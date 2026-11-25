import logging
import os
import time
from datetime import date, datetime, timedelta, timezone

from django.core.management.base import BaseCommand

from api.models import FirmsAreaRequest, FirmsCheckpoint, FirmsPipelineState
from api.services.firms import (
    BRAZIL_AREA,
    CALIBRATION_BOUNDS,
    SOURCES,
    FirmsError,
    calculate_calibration,
    download_source_range,
    harmonize_range,
    history_start_date,
    published_source_intervals,
    source_last_day,
)

logger = logging.getLogger(__name__)
BACKFILL_CHUNKS_PER_CYCLE = 4
BACKFILL_PAUSE_SECONDS = 10
DAILY_SYNC_INTERVAL = timedelta(hours=24)


def _brazil_backfill_enabled():
    return os.environ.get("FIRMS_BRAZIL_BACKFILL_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _pipeline_state():
    state, _ = FirmsPipelineState.objects.get_or_create(pk=1)
    return state


def _clamp_checkpoint(checkpoint, source_end):
    next_publishable = source_end + timedelta(days=1)
    if checkpoint.next_date > next_publishable:
        # Older workers advanced checkpoints against today's date instead of the archive.
        checkpoint.next_date = next_publishable
        checkpoint.save(update_fields=["next_date", "updated_at"])


def _run_backfill_batch(state, today):
    window_start = history_start_date(today)
    published = published_source_intervals()
    checkpoints = {}
    for source, first_day in SOURCES:
        source_start = max(first_day, window_start, published[source][0])
        checkpoint, _ = FirmsCheckpoint.objects.get_or_create(
            source=source,
            defaults={"next_date": source_start},
        )
        checkpoints[source] = checkpoint

    processed = 0
    for source, first_day in SOURCES:
        checkpoint = checkpoints[source]
        source_end = source_last_day(source, min(today, published[source][1]))
        _clamp_checkpoint(checkpoint, source_end)
        while checkpoint.next_date <= source_end and processed < BACKFILL_CHUNKS_PER_CYCLE:
            start = max(checkpoint.next_date, published[source][0])
            if start > source_end:
                break
            end = min(start + timedelta(days=4), source_end)
            state.status = "backfilling"
            state.active_source = source
            state.last_error = ""
            state.save(update_fields=["status", "active_source", "last_error", "updated_at"])
            download_source_range(source, start, end, BRAZIL_AREA)
            checkpoint.next_date = end + timedelta(days=1)
            checkpoint.save(update_fields=["next_date", "updated_at"])
            processed += 1
        if processed >= BACKFILL_CHUNKS_PER_CYCLE:
            break

    complete = all(
        max(checkpoints[source].next_date, published[source][0])
        > source_last_day(source, min(today, published[source][1]))
        for source, _ in SOURCES
    )
    if complete and not state.initial_backfill_complete:
        state.status = "harmonizing"
        state.active_source = ""
        state.save(update_fields=["status", "active_source", "updated_at"])
        calculate_calibration()
        harmonize_range(max(SOURCES[0][1], window_start), today)
        state.initial_backfill_complete = True
        state.last_sync_at = datetime.now(timezone.utc)
        state.status = "ready"
        state.save(
            update_fields=[
                "initial_backfill_complete",
                "last_sync_at",
                "status",
                "updated_at",
            ]
        )
        logger.info("Carga histórica e harmonização inicial concluídas.")
    return complete


def _run_daily_sync(state, today):
    published = published_source_intervals()
    state.status = "syncing"
    state.active_source = ""
    state.last_error = ""
    state.save(update_fields=["status", "active_source", "last_error", "updated_at"])
    for source, first_day in SOURCES:
        published_start, published_end = published[source]
        source_end = source_last_day(source, min(today, published_end))
        checkpoint, _ = FirmsCheckpoint.objects.get_or_create(
            source=source,
            defaults={"next_date": max(first_day, published_start, source_end - timedelta(days=4))},
        )
        _clamp_checkpoint(checkpoint, source_end)
        cursor = max(checkpoint.next_date, first_day, published_start)
        while cursor <= source_end:
            end = min(cursor + timedelta(days=4), source_end)
            download_source_range(source, cursor, end, BRAZIL_AREA)
            harmonize_range(cursor, end)
            cursor = end + timedelta(days=1)
            checkpoint.next_date = cursor
            checkpoint.save(update_fields=["next_date", "updated_at"])
    state.last_sync_at = datetime.now(timezone.utc)
    state.status = "ready"
    state.save(update_fields=["last_sync_at", "status", "updated_at"])


def _run_area_request_batch(download_sources=None):
    requests = FirmsAreaRequest.objects.filter(
        status__in=("queued", "downloading", "harmonizing")
    )
    if download_sources is not None:
        requests = requests.filter(download_sources=download_sources)
    request = requests.first()
    if not request:
        return False

    processing_status = "downloading" if request.download_sources else "harmonizing"
    request.status = processing_status
    request.last_error = ""
    request.save(update_fields=["status", "last_error", "updated_at"])
    chunk_end = min(request.next_date + timedelta(days=4), request.end_date)
    area = f"{request.west},{request.south},{request.east},{request.north}"
    bounds = (request.south, request.north, request.west, request.east)
    try:
        omitted = []
        if request.download_sources:
            published = published_source_intervals()
            for source, first_day in SOURCES:
                published_start, published_end = published[source]
                source_start = max(request.next_date, first_day, published_start)
                source_end = source_last_day(source, min(chunk_end, published_end))
                nominal_start = max(request.start_date, first_day)
                nominal_end = source_last_day(source, request.end_date)
                if nominal_start <= nominal_end and (
                    nominal_start < published_start or nominal_end > published_end
                ):
                    omitted.append(f"{source} publicado de {published_start} a {published_end}")

                if source_start <= source_end:
                    download_source_range(source, source_start, source_end, area)
        if chunk_end >= request.end_date:
            scope_south, scope_north, scope_west, scope_east = CALIBRATION_BOUNDS
            overlaps_calibration_scope = (
                request.south <= scope_north
                and request.north >= scope_south
                and request.west <= scope_east
                and request.east >= scope_west
            )
            if request.download_sources and overlaps_calibration_scope:
                calculate_calibration()
                harmonize_range(request.start_date, chunk_end, bounds=bounds)
            else:
                harmonize_range(request.next_date, chunk_end, bounds=bounds)
            request.status = "partial" if omitted else "ready"
            request.last_error = ". ".join(omitted)
        else:
            harmonize_range(request.next_date, chunk_end, bounds=bounds)
            request.next_date = chunk_end + timedelta(days=1)
            request.status = processing_status
        request.save(update_fields=["status", "next_date", "last_error", "updated_at"])
        return True
    except FirmsError as error:
        request.status = "error"
        request.last_error = str(error)
        request.save(update_fields=["status", "last_error", "updated_at"])
        logger.error("Solicitação FIRMS %s falhou: %s", request.pk, error)
        return True


class Command(BaseCommand):
    help = "Baixa, harmoniza e atualiza diariamente os dados MODIS/VIIRS da NASA FIRMS."

    def handle(self, *args, **options):
        while True:
            state = _pipeline_state()
            if not os.environ.get("FIRMS_MAP_KEY", "").strip():
                if _run_area_request_batch(download_sources=False):
                    time.sleep(BACKFILL_PAUSE_SECONDS)
                    continue
                state.status = "waiting_for_key"
                state.active_source = ""
                state.last_error = "Configure FIRMS_MAP_KEY no arquivo .env."
                state.save(update_fields=["status", "active_source", "last_error", "updated_at"])
                logger.warning("FIRMS_MAP_KEY ausente; aguardando configuração no .env.")
                time.sleep(300)
                continue

            today = datetime.now(timezone.utc).date()
            try:
                if _run_area_request_batch():
                    time.sleep(BACKFILL_PAUSE_SECONDS)
                    continue

                if not _brazil_backfill_enabled():
                    if state.status != "on_demand" or state.active_source or state.last_error:
                        state.status = "on_demand"
                        state.active_source = ""
                        state.last_error = ""
                        state.save(
                            update_fields=["status", "active_source", "last_error", "updated_at"]
                        )
                    time.sleep(60)
                    continue

                if not state.initial_backfill_complete:
                    complete = _run_backfill_batch(state, today)
                    time.sleep(BACKFILL_PAUSE_SECONDS if not complete else 60)
                elif (
                    state.last_sync_at is None
                    or datetime.now(timezone.utc) - state.last_sync_at >= DAILY_SYNC_INTERVAL
                ):
                    _run_daily_sync(state, today)
                    time.sleep(60)
                else:
                    remaining = DAILY_SYNC_INTERVAL - (
                        datetime.now(timezone.utc) - state.last_sync_at
                    )
                    time.sleep(min(remaining.total_seconds(), 3600))
            except FirmsError as error:
                logger.error("Sincronização FIRMS interrompida: %s", error)
                state.status = "error"
                state.last_error = str(error)
                state.save(update_fields=["status", "last_error", "updated_at"])
                time.sleep(300)
            except Exception:
                logger.exception("Falha inesperada na sincronização/harmonização FIRMS.")
                state.status = "error"
                state.last_error = "Falha inesperada; consulte os logs do serviço firms-sync."
                state.save(update_fields=["status", "last_error", "updated_at"])
                time.sleep(300)
