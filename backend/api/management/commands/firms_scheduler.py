import logging
import os
import time
from datetime import date, datetime, timedelta, timezone

from django.core.management.base import BaseCommand

from api.models import FirmsAreaRequest, FirmsCheckpoint, FirmsPipelineState
from api.services.firms import (
    BRAZIL_AREA,
    SOURCES,
    FirmsError,
    calculate_calibration,
    download_source_range,
    harmonize_range,
    history_start_date,
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


def _run_backfill_batch(state, today):
    window_start = history_start_date(today)
    checkpoints = {}
    for source, first_day in SOURCES:
        source_start = max(first_day, window_start)
        checkpoint, _ = FirmsCheckpoint.objects.get_or_create(
            source=source,
            defaults={"next_date": source_start},
        )
        checkpoints[source] = checkpoint

    processed = 0
    for source, first_day in SOURCES:
        checkpoint = checkpoints[source]
        while checkpoint.next_date <= today and processed < BACKFILL_CHUNKS_PER_CYCLE:
            start = checkpoint.next_date
            end = min(start + timedelta(days=4), today)
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

    complete = all(checkpoints[source].next_date > today for source, _ in SOURCES)
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
    start = max(today - timedelta(days=4), SOURCES[0][1])
    state.status = "syncing"
    state.active_source = ""
    state.last_error = ""
    state.save(update_fields=["status", "active_source", "last_error", "updated_at"])
    for source, first_day in SOURCES:
        source_start = max(start, first_day)
        if source_start <= today:
            download_source_range(source, source_start, today, BRAZIL_AREA)
    harmonize_range(start, today)
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
    try:
        if request.download_sources:
            for source, first_day in SOURCES:
                source_start = max(request.next_date, first_day)
                if source_start <= chunk_end:
                    download_source_range(source, source_start, chunk_end, area)
        bounds = (request.south, request.north, request.west, request.east)
        harmonize_range(request.next_date, chunk_end, bounds=bounds)
        if chunk_end >= request.end_date:
            request.status = "ready"
        else:
            request.next_date = chunk_end + timedelta(days=1)
            request.status = processing_status
        request.save(update_fields=["status", "next_date", "updated_at"])
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
