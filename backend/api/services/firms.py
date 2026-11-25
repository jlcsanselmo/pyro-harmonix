import csv
import gzip
import hashlib
import io
import json
import logging
import math
import os
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime, time as day_time, timedelta, timezone
from decimal import Decimal, DecimalException
from functools import lru_cache
from pathlib import Path
from tempfile import NamedTemporaryFile

import h3
from django.db import connection, transaction
from django.db.models import Count, Max, Min, Q, Sum
from django.db.models.functions import TruncDate

from api.models import FirmsDetection, FirmsDownload, Hotspot, RegionalSensorCalibration
from api.services.observation import Observation, fuse_observations

logger = logging.getLogger(__name__)

FIRMS_API_ROOT = "https://firms.modaps.eosdis.nasa.gov/api"
FIRMS_API = f"{FIRMS_API_ROOT}/area/csv"
BRAZIL_AREA = "-74,-34,-34,6"
MAX_DAYS_PER_REQUEST = 5
MAX_RESPONSE_BYTES = 200 * 1024 * 1024
REQUEST_DELAY_SECONDS = 3
ESTIMATE_BASE_SECONDS_PER_REQUEST = (60, 180)
ESTIMATE_REFERENCE_AREA_DEGREES = 12
H3_RESOLUTION = 8
CALIBRATION_H3_RESOLUTION = 7
HARMONIZED_H3_RESOLUTION = CALIBRATION_H3_RESOLUTION
AQUA_START = date(2002, 7, 4)
AQUA_END = None
SNPP_START = date(2012, 1, 20)
# FIRMS announced the end of S-NPP delivery from 2026-11-02.
SNPP_END = date(2026, 11, 1)
CALIBRATION_SCOPE = "altinopolis-pitangueiras"
CALIBRATION_SCOPE_LABEL = "Altinópolis–Pitangueiras · Cerrado/interior de SP"
CALIBRATION_BOUNDS = (
    Decimal("-21.215243"),
    Decimal("-20.8087035"),
    Decimal("-48.433"),
    Decimal("-47.181633"),
)
CALIBRATION_SHRINKAGE_PRIOR_PAIRS = 30
CALIBRATION_BOOTSTRAP_REPLICATES = 500
CALIBRATION_PAIR_MODE = "union"
CALIBRATION_PAIR_MODES = frozenset(("union", "codetect"))
FUSION_METHODS = ("present_average", "zero_filled_mean", "maximum")
SERIES_METHOD = "detection_conditioned_v1"
CALIBRATION_METHOD = "monthly_shrunk_union"
CALIBRATION_FIRST_YEAR = 2019
CALIBRATION_LAST_YEAR = 2024
MIN_ANNUAL_CALIBRATION_PAIRS = 30
MIN_CALIBRATION_YEARS = 5
MIN_OVERLAP_STRATA_PER_YEAR = 5
HISTORY_YEARS = 5
SOURCES = (
    ("MODIS_SP", date(2000, 11, 1)),
    ("VIIRS_SNPP_SP", date(2012, 1, 20)),
)


class FirmsError(Exception):
    pass


class FirmsResponseTooLarge(FirmsError):
    pass


def sensors_operating(day):
    aqua_on = day >= AQUA_START and (AQUA_END is None or day <= AQUA_END)
    snpp_on = day >= SNPP_START and (SNPP_END is None or day <= SNPP_END)
    return aqua_on, snpp_on


def _calibration_factor_is_usable(calibration):
    return bool(
        calibration
        and calibration.calibrated
        and math.isfinite(calibration.factor)
        and calibration.factor >= 0
    )


def published_source_intervals():
    """Cache the FIRMS archive limits by UTC hour in the worker process."""
    utc_hour = int(datetime.now(timezone.utc).timestamp()) // 3600
    return _published_source_intervals(utc_hour)


@lru_cache(maxsize=1)
def _published_source_intervals(_utc_hour):
    map_key = os.environ.get("FIRMS_MAP_KEY", "").strip()
    if not map_key:
        raise FirmsError("FIRMS_MAP_KEY não configurada.")
    key = urllib.parse.quote(map_key, safe="")
    url = f"{FIRMS_API_ROOT}/data_availability/csv/{key}/ALL"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            content = response.read(64 * 1024 + 1)
        if len(content) > 64 * 1024:
            raise ValueError("oversized availability response")
        return _parse_published_intervals(content.decode("utf-8-sig"))
    except (OSError, UnicodeDecodeError, ValueError, KeyError, csv.Error) as error:
        raise FirmsError(f"Falha ao verificar a disponibilidade FIRMS ({type(error).__name__}).") from None


def _parse_published_intervals(content):
    intervals = {}
    supported = dict(SOURCES)
    for row in csv.DictReader(io.StringIO(content)):
        source = row["data_id"]
        if source in supported:
            start = date.fromisoformat(row["min_date"] or "")
            end = date.fromisoformat(row["max_date"] or "")
            if start > end or source in intervals:
                raise ValueError("invalid availability interval")
            intervals[source] = (start, end)
    if intervals.keys() != supported.keys():
        raise ValueError("missing FIRMS Standard Processing product")
    return intervals


def source_last_day(source, requested_end):
    if source == "VIIRS_SNPP_SP" and SNPP_END is not None:
        return min(requested_end, SNPP_END)
    return requested_end


def estimate_area_download(start, end, south, north, west, east):
    api_requests = 0
    sources = []
    for source, first_day in SOURCES:
        source_start = max(start, first_day)
        source_end = source_last_day(source, end)
        if source_start <= source_end:
            days = (source_end - source_start).days + 1
            api_requests += (days + MAX_DAYS_PER_REQUEST - 1) // MAX_DAYS_PER_REQUEST
            sources.append(source)

    area_degrees = float((north - south) * (east - west))
    area_factor = max(0.5, math.sqrt(area_degrees / ESTIMATE_REFERENCE_AREA_DEGREES))
    minimum_seconds = math.ceil(api_requests * ESTIMATE_BASE_SECONDS_PER_REQUEST[0] * area_factor)
    maximum_seconds = math.ceil(api_requests * ESTIMATE_BASE_SECONDS_PER_REQUEST[1] * area_factor)
    return {
        "api_requests": api_requests,
        "sources": sources,
        "estimated_seconds_min": minimum_seconds,
        "estimated_seconds_max": maximum_seconds,
    }


def history_start_date(today=None):
    today = today or datetime.now(timezone.utc).date()
    year = today.year - HISTORY_YEARS
    try:
        return today.replace(year=year)
    except ValueError:
        return today.replace(year=year, day=28)


def _parse_acquired_at(row):
    acquired_date = date.fromisoformat(row["acq_date"].strip())
    raw_time = row["acq_time"].strip()
    if ":" in raw_time:
        acquired_time = day_time.fromisoformat(raw_time)
        if acquired_time.tzinfo is not None:
            raise ValueError("FIRMS acquisition time must be UTC HHMM or HH:MM")
    else:
        if not 1 <= len(raw_time) <= 4 or not raw_time.isascii() or not raw_time.isdigit():
            raise ValueError("Invalid FIRMS acquisition time")
        acquired_time = datetime.strptime(raw_time.zfill(4), "%H%M").time()
    return datetime.combine(acquired_date, acquired_time, tzinfo=timezone.utc)


def iter_firms_csv(content, source):
    if source not in dict(SOURCES):
        raise FirmsError("Produto FIRMS sem schema suportado.")
    reader = csv.DictReader(io.StringIO(content.lstrip("\ufeff")))
    if not reader.fieldnames:
        raise FirmsError("A resposta da FIRMS não contém cabeçalho CSV.")

    fields = [field.strip().lower() for field in reader.fieldnames]
    required = {"latitude", "longitude", "acq_date", "acq_time"}
    if len(set(fields)) != len(fields) or not required.issubset(fields):
        raise FirmsError("A FIRMS retornou um CSV sem as colunas de localização e aquisição esperadas.")

    unique = {}
    for line_number, raw_row in enumerate(reader, start=2):
        row = {
            key.strip().lower(): (value or "").strip()
            for key, value in raw_row.items()
            if key
        }
        try:
            latitude = Decimal(row["latitude"])
            longitude = Decimal(row["longitude"])
            if not latitude.is_finite() or not longitude.is_finite():
                raise ValueError("coordenadas não finitas")
            if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
                raise ValueError("coordenadas fora dos limites")
            acquired_at = _parse_acquired_at(row)
            cell = h3.latlng_to_cell(float(latitude), float(longitude), H3_RESOLUTION)
            frp_text = row.get("frp", "")
            frp = float(frp_text) if frp_text else None
            if frp is not None and (not math.isfinite(frp) or frp < 0):
                raise ValueError("FRP inválida")
        except (KeyError, ValueError, OverflowError, DecimalException) as error:
            raise FirmsError(f"Registro FIRMS inválido na linha {line_number}: {error}") from None

        identity = "|".join(
            (
                source,
                acquired_at.isoformat(),
                str(latitude.quantize(Decimal("0.00001"))),
                str(longitude.quantize(Decimal("0.00001"))),
                row.get("satellite", ""),
                row.get("scan", ""),
                row.get("track", ""),
            )
        )
        fingerprint = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        turn = row.get("daynight", "").upper()
        unique[fingerprint] = FirmsDetection(
            source=source,
            latitude=latitude,
            longitude=longitude,
            acquired_at=acquired_at,
            grid_cell=cell,
            confidence=row.get("confidence", "")[:32],
            frp=frp,
            daynight=turn if turn in ("D", "N") else "",
            fingerprint=fingerprint,
            attributes=row,
        )
        if len(unique) >= 2000:
            yield from unique.values()
            unique.clear()
    yield from unique.values()


def parse_firms_csv(content, source):
    return list(iter_firms_csv(content, source))


def _request_csv(source, start, day_range, area):
    map_key = os.environ.get("FIRMS_MAP_KEY", "").strip()
    if not map_key:
        raise FirmsError("FIRMS_MAP_KEY não configurada. Copie .env.example para .env e informe sua chave.")

    escaped_key = urllib.parse.quote(map_key, safe="")
    escaped_area = urllib.parse.quote(area, safe=",")
    url = f"{FIRMS_API}/{escaped_key}/{source}/{escaped_area}/{day_range}/{start.isoformat()}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "PyroHarmonix/0.1 (NASA Space Apps Challenge)"},
    )
    try:
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                body = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as error:
            raise FirmsError(f"NASA FIRMS respondeu HTTP {error.code} para {source} em {start}.") from None
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise FirmsError(
                f"Falha de comunicação com NASA FIRMS para {source} em {start} "
                f"({type(error).__name__})."
            ) from None
    finally:
        time.sleep(REQUEST_DELAY_SECONDS)

    if len(body) > MAX_RESPONSE_BYTES:
        raise FirmsResponseTooLarge(
            f"A resposta da FIRMS para {source} em {start} excedeu 200 MB; "
            "reduza o intervalo ou divida a área de coleta."
        )
    try:
        content = body.decode("utf-8")
    except UnicodeDecodeError:
        raise FirmsError(f"A resposta da FIRMS para {source} em {start} não está em UTF-8.") from None
    return content


def download_source_range(source, start, end, area=BRAZIL_AREA):
    day_range = (end - start).days + 1
    if not 1 <= day_range <= MAX_DAYS_PER_REQUEST:
        raise FirmsError("Cada solicitação à FIRMS deve abranger de 1 a 5 dias.")

    try:
        content = _request_csv(source, start, day_range, area)
    except FirmsResponseTooLarge:
        if day_range == 1:
            raise
        midpoint = start + timedelta(days=day_range // 2 - 1)
        first_count = download_source_range(source, start, midpoint, area)
        second_count = download_source_range(source, midpoint + timedelta(days=1), end, area)
        return first_count + second_count

    received = _store_download(content, source, start, end, area)
    logger.info("FIRMS %s %s..%s (%s): %s registros recebidos", source, start, end, area, received)
    return received


@transaction.atomic
def _store_download(content, source, start, end, area):
    west, south, east, north = map(Decimal, area.split(",")) if area != "world" else (
        -180, -90, 180, 90,
    )
    batch = []
    received = 0
    for detection in iter_firms_csv(content, source):
        if not start <= detection.acquired_at.date() <= end or not (
            south <= detection.latitude <= north and west <= detection.longitude <= east
        ):
            raise FirmsError(f"FIRMS retornou detecções fora da janela solicitada ({source}, {start}..{end}).")
        batch.append(detection)
        if len(batch) == 2000:
            _upsert_detections(batch)
            received += len(batch)
            batch.clear()
    if batch:
        _upsert_detections(batch)
        received += len(batch)
    payload = content.encode("utf-8")
    checksum = hashlib.sha256(payload).hexdigest()
    archived = _archive_download(payload, checksum)
    receipt, created = FirmsDownload.objects.get_or_create(
        source=source, start_date=start, end_date=end, area=area, sha256=checksum,
        defaults={"received_rows": received, "archived": archived},
    )
    if not created and archived and not receipt.archived:
        FirmsDownload.objects.filter(pk=receipt.pk).update(archived=True)
    return received


def _archive_download(payload, checksum):
    root = os.environ.get("FIRMS_RAW_ARCHIVE_DIR")
    if not root:
        return False
    target = Path(root) / f"{checksum}.csv.gz"
    if target.exists():
        return True
    temp_path = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=target.parent, delete=False) as output:
            temp_path = Path(output.name)
            with gzip.GzipFile(filename="", fileobj=output, mode="wb", mtime=0) as archive:
                archive.write(payload)
        temp_path.replace(target)
    except OSError:
        raise FirmsError("Falha ao arquivar a resposta bruta FIRMS.") from None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    return True


def _upsert_detections(rows):
    unique = {row.fingerprint: row for row in rows}
    with transaction.atomic():
        FirmsDetection.objects.bulk_create(
            list(unique.values()),
            batch_size=2000,
            update_conflicts=True,
            unique_fields=["fingerprint"],
            update_fields=[
                "latitude",
                "longitude",
                "acquired_at",
                "grid_cell",
                "confidence",
                "frp",
                "daynight",
                "attributes",
            ],
        )


def _calibration_scope_filter():
    south, north, west, east = CALIBRATION_BOUNDS
    return Q(
        latitude__gte=south,
        latitude__lte=north,
        longitude__gte=west,
        longitude__lte=east,
    )


def _calibration_detection_queryset():
    eligible_sources = (
        Q(source="MODIS_SP", attributes__satellite="Aqua")
        | Q(source="VIIRS_SNPP_SP", attributes__satellite="N")
    )
    return FirmsDetection.objects.filter(
        _calibration_scope_filter(),
        acquired_at__gte=datetime(CALIBRATION_FIRST_YEAR, 1, 1, tzinfo=timezone.utc),
        acquired_at__lt=datetime(CALIBRATION_LAST_YEAR + 1, 1, 1, tzinfo=timezone.utc),
    ).filter(eligible_sources)


def _calibration_overlap_years(groups):
    strata_by_year = defaultdict(int)
    for (_, day, _, _), values in groups.items():
        if values[0] and values[1]:
            strata_by_year[day.year] += 1
    return sorted(
        year
        for year, strata_count in strata_by_year.items()
        if strata_count >= MIN_OVERLAP_STRATA_PER_YEAR
    )


def regional_calibration_records():
    rows = list(
        RegionalSensorCalibration.objects.filter(scope=CALIBRATION_SCOPE)
        .order_by("month", "metric")
    )
    if len(rows) == 24:
        return rows
    if rows:
        logger.warning(
            "Tabela de calibração regional incompleta (%s/24); usando o snapshot versionado.",
            len(rows),
        )

    snapshot_path = Path(__file__).resolve().parents[1] / "data" / "regional_sensor_calibration.json"
    with snapshot_path.open(encoding="utf-8") as snapshot_file:
        snapshot = json.load(snapshot_file)
    records = []
    for fields in snapshot["calibrations"]:
        values = dict(fields)
        for field in ("overlap_start", "overlap_end"):
            if values[field]:
                values[field] = date.fromisoformat(values[field])
        records.append(RegionalSensorCalibration(scope=snapshot["scope"], **values))
    return records


def _source_parent(cell, resolution):
    if not h3.is_valid_cell(cell) or h3.get_resolution(cell) != H3_RESOLUTION:
        raise FirmsError(f"Detecção FIRMS com célula inválida para H3 res. {H3_RESOLUTION}: {cell!r}")
    return h3.cell_to_parent(cell, resolution)


def _build_calibration_groups(queryset, resolution=CALIBRATION_H3_RESOLUTION):
    if not 0 <= resolution <= H3_RESOLUTION:
        raise ValueError(f"Unsupported calibration H3 resolution: {resolution}")

    groups = defaultdict(lambda: [0, 0, 0.0, 0.0, 0, 0])
    observations = queryset.annotate(
        acquired_date=TruncDate("acquired_at", tzinfo=timezone.utc)
    ).values(
        "acquired_date",
        "grid_cell",
        "source",
        "frp",
        "daynight",
    ).order_by().iterator(chunk_size=5000)
    for row in observations:
        index = 0 if row["source"] == "MODIS_SP" else 1
        day = row["acquired_date"]
        parent = _source_parent(row["grid_cell"], resolution)
        values = groups[(day.month, day, parent, row["daynight"])]
        values[index] += 1
        values[index + 2] += row["frp"] or 0.0
        values[index + 4] += row["frp"] is not None
    return groups


def _build_calibration_pairs(groups, pair_mode=None, *, legacy_frp=False):
    pair_mode = CALIBRATION_PAIR_MODE if pair_mode is None else pair_mode
    if pair_mode not in CALIBRATION_PAIR_MODES:
        raise ValueError(f"Unsupported calibration pair mode: {pair_mode}")

    month_pairs = {
        "count": defaultdict(list),
        "frp": defaultdict(list),
    }
    all_pairs = {"count": [], "frp": []}
    for (month, day, _, turn), values in groups.items():
        has_pair = (
            bool(values[0] or values[1])
            if pair_mode == "union"
            else bool(values[0] and values[1] and turn in ("D", "N"))
        )
        if has_pair:
            pair = (values[0], values[1], day)
            month_pairs["count"][month].append(pair)
            all_pairs["count"].append(pair)

            complete_frp = (
                len(values) < 6 or (values[4] == values[0] and values[5] == values[1])
            )
            if (complete_frp or legacy_frp) and (values[2] or values[3]):
                frp_pair = (values[2], values[3], day)
                month_pairs["frp"][month].append(frp_pair)
                all_pairs["frp"].append(frp_pair)

    return month_pairs, all_pairs


def _ratio_of_sums(pairs):
    denominator = sum(pair[1] for pair in pairs)
    if not denominator:
        return None
    return sum(pair[0] for pair in pairs) / denominator


def _fuse_measurement(modis, viirs, factor, method):
    """Historical count comparison, including the circular zero-fill diagnostic."""
    if method not in FUSION_METHODS:
        raise ValueError(f"Unsupported fusion method: {method}")
    adjusted_viirs = viirs * factor
    if method == "zero_filled_mean":
        return (modis + adjusted_viirs) / 2
    if method == "maximum":
        return max(modis, adjusted_viirs)
    if modis and viirs:
        return (modis + adjusted_viirs) / 2
    return modis or adjusted_viirs


def _shrinkage_weight(sample_size):
    return sample_size / (
        sample_size + CALIBRATION_SHRINKAGE_PRIOR_PAIRS
    ) if sample_size else 0


def _bootstrap_factor_interval(
    pairs_by_month, metric, *, replicates=None, block_days=1,
):
    replicates = CALIBRATION_BOOTSTRAP_REPLICATES if replicates is None else replicates
    if replicates < 1 or block_days < 1:
        raise ValueError("Bootstrap replicates and block size must be positive")
    daily_sums_by_month = {}
    pair_counts_by_month = {}
    for month in sorted(pairs_by_month):
        sums_by_day = defaultdict(lambda: [0.0, 0.0, 0])
        for modis, viirs, day in pairs_by_month[month]:
            cluster = (day.year, (day.day - 1) // block_days)
            daily_sums = sums_by_day[cluster]
            daily_sums[0] += modis
            daily_sums[1] += viirs
            daily_sums[2] += 1
        daily_sums_by_month[month] = [
            (day, *sums_by_day[day])
            for day in sorted(sums_by_day)
        ]
        pair_counts_by_month[month] = sum(
            daily_sums[3] for daily_sums in daily_sums_by_month[month]
        )

    estimates_by_month = {month: [] for month in range(1, 13)}
    if not any(daily_sums_by_month.values()):
        return {month: (None, None) for month in range(1, 13)}

    seed = 2024 + (0 if metric == "count" else 1)
    generator = random.Random(seed)
    for _ in range(replicates):
        sampled_month_sums = {}
        annual_modis = 0.0
        annual_viirs = 0.0
        for month in sorted(daily_sums_by_month):
            daily_sums = daily_sums_by_month[month]
            selected_days = generator.choices(daily_sums, k=len(daily_sums))
            month_modis = sum(day_sums[1] for day_sums in selected_days)
            month_viirs = sum(day_sums[2] for day_sums in selected_days)
            sampled_month_sums[month] = (month_modis, month_viirs)
            annual_modis += month_modis
            annual_viirs += month_viirs

        if not annual_viirs:
            continue
        annual_factor = annual_modis / annual_viirs
        for month in range(1, 13):
            month_modis, month_viirs = sampled_month_sums.get(month, (0.0, 0.0))
            month_factor = month_modis / month_viirs if month_viirs else None
            if month_factor is None:
                estimate = annual_factor
            else:
                weight = _shrinkage_weight(pair_counts_by_month.get(month, 0))
                estimate = weight * month_factor + (1 - weight) * annual_factor
            estimates_by_month[month].append(estimate)

    intervals = {}
    for month, estimates in estimates_by_month.items():
        if not estimates:
            intervals[month] = (None, None)
            continue
        estimates.sort()
        lower = estimates[int(0.025 * (len(estimates) - 1))]
        upper = estimates[int(0.975 * (len(estimates) - 1))]
        intervals[month] = (lower, upper)
    return intervals


def export_calibration_snapshot(path, groups=None):
    records = regional_calibration_records()
    current_snapshot_path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "regional_sensor_calibration.json"
    )
    overlap_years = []
    if current_snapshot_path.exists():
        with current_snapshot_path.open(encoding="utf-8") as snapshot_file:
            overlap_years = json.load(snapshot_file).get("overlap_years", [])
    database_record_count = RegionalSensorCalibration.objects.filter(
        scope=CALIBRATION_SCOPE
    ).count()
    if database_record_count == 24 and groups is not None:
        overlap_years = _calibration_overlap_years(groups)
    fields = (
        "month",
        "metric",
        "factor",
        "sample_size",
        "modis_measure",
        "viirs_measure",
        "ci_lower",
        "ci_upper",
        "fallback_level",
        "h3_resolution",
        "overlap_start",
        "overlap_end",
        "calibrated",
        "fusion_average",
        "fusion_maximum",
        "fusion_zero_filled",
        "fusion_union_parent_days",
        "fusion_parent_days",
    )
    serialized_records = []
    for record in records:
        values = {}
        for field in fields:
            value = getattr(record, field)
            if isinstance(value, date):
                value = value.isoformat()
            values[field] = value
        serialized_records.append(values)

    overlap_dates = [
        getattr(record, field)
        for record in records
        for field in ("overlap_start", "overlap_end")
        if getattr(record, field)
    ]
    snapshot = {
        "scope": CALIBRATION_SCOPE,
        "scope_label": CALIBRATION_SCOPE_LABEL,
        "h3_resolution": CALIBRATION_H3_RESOLUTION,
        "shrinkage_prior_pairs": CALIBRATION_SHRINKAGE_PRIOR_PAIRS,
        "bootstrap_replicates": CALIBRATION_BOOTSTRAP_REPLICATES,
        "pair_mode": CALIBRATION_PAIR_MODE,
        "bootstrap_unit": "day",
        "overlap_years": overlap_years,
        "overlap_start": min(overlap_dates).isoformat() if overlap_dates else None,
        "overlap_end": max(overlap_dates).isoformat() if overlap_dates else None,
        "calibrations": serialized_records,
    }
    snapshot_path = Path(path)
    with snapshot_path.open("w", encoding="utf-8") as snapshot_file:
        json.dump(snapshot, snapshot_file, indent=2, ensure_ascii=False)
        snapshot_file.write("\n")
    return snapshot_path


@transaction.atomic
@transaction.atomic
def calculate_calibration(groups=None):
    overlap = _calibration_detection_queryset()
    date_range = overlap.aggregate(first=Min("acquired_at"), last=Max("acquired_at"))
    overlap_start = date_range["first"].date() if date_range["first"] else None
    overlap_end = date_range["last"].date() if date_range["last"] else None
    if not overlap_start:
        return regional_calibration_records()

    if groups is None:
        groups = _build_calibration_groups(overlap)
    month_pairs, all_pairs = _build_calibration_pairs(groups)
    overlap_years = _calibration_overlap_years(groups)

    if any(
        len(all_pairs[metric]) < MIN_ANNUAL_CALIBRATION_PAIRS
        for metric in ("count", "frp")
    ) or len(overlap_years) < MIN_CALIBRATION_YEARS:
        logger.warning(
            "A calibração regional existente foi preservada: são necessários %s pares "
            "anuais e sobreposição dos sensores em %s anos.",
            MIN_ANNUAL_CALIBRATION_PAIRS,
            MIN_CALIBRATION_YEARS,
        )
        return regional_calibration_records()

    factors = {}
    for metric in ("count", "frp"):
        annual_pairs = all_pairs[metric]
        annual_factor = _ratio_of_sums(annual_pairs)
        confidence_intervals = _bootstrap_factor_interval(
            month_pairs[metric],
            metric,
        )
        for month in range(1, 13):
            pairs = month_pairs[metric][month]
            sample_size = len(pairs)
            month_factor = _ratio_of_sums(pairs)
            weight = _shrinkage_weight(sample_size)
            if annual_factor is not None:
                factor = (
                    weight * month_factor + (1 - weight) * annual_factor
                    if month_factor is not None
                    else annual_factor
                )
                fallback_level = (
                    "monthly_shrunk"
                    if month_factor is not None
                    else "regional_annual"
                )
                calibrated = True
                ci_lower, ci_upper = confidence_intervals[month]
            else:
                factor = 1.0
                fallback_level = "neutral"
                calibrated = False
                ci_lower = ci_upper = None

            factors[(month, metric)] = factor
            RegionalSensorCalibration.objects.update_or_create(
                scope=CALIBRATION_SCOPE,
                month=month,
                metric=metric,
                defaults={
                    "factor": factor,
                    "sample_size": sample_size,
                    "modis_measure": sum(pair[0] for pair in pairs),
                    "viirs_measure": sum(pair[1] for pair in pairs),
                    "ci_lower": ci_lower,
                    "ci_upper": ci_upper,
                    "fallback_level": fallback_level,
                    "h3_resolution": CALIBRATION_H3_RESOLUTION,
                    "overlap_start": overlap_start,
                    "overlap_end": overlap_end,
                    "calibrated": calibrated,
                    "fusion_average": None,
                    "fusion_maximum": None,
                    "fusion_zero_filled": None,
                    "fusion_union_parent_days": None,
                    "fusion_parent_days": None,
                },
            )

    for month in range(1, 13):
        month_groups = [
            (day, parent, values)
            for (group_month, day, parent, _), values in groups.items()
            if group_month == month
        ]
        factor = factors[(month, "count")]
        average = 0.0
        maximum = 0.0
        zero_filled = 0.0
        for _, _, values in month_groups:
            modis_count, viirs_count = values[:2]
            average += _fuse_measurement(
                modis_count,
                viirs_count,
                factor,
                "present_average",
            )
            maximum += _fuse_measurement(
                modis_count,
                viirs_count,
                factor,
                "maximum",
            )
            zero_filled += _fuse_measurement(
                modis_count,
                viirs_count,
                factor,
                "zero_filled_mean",
            )
        RegionalSensorCalibration.objects.filter(
            scope=CALIBRATION_SCOPE,
            month=month,
            metric="count",
        ).update(
            fusion_average=average,
            fusion_maximum=maximum,
            fusion_zero_filled=zero_filled,
            fusion_union_parent_days=len({(day, parent) for day, parent, _ in month_groups}),
            fusion_parent_days=len(month_groups),
        )

    return regional_calibration_records()


@transaction.atomic
def harmonize_window(start, end, bounds=None):
    if connection.vendor == "postgresql":
        # Serialize overlapping rebuilds before either transaction reads derived rows.
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s, %s)", [1486378197, 1])
    if start < AQUA_START or AQUA_END is not None and start > AQUA_END:
        logger.warning(
            "Aqua is not operating for part of %s..%s; pre/post-operation dates produce no Aqua-basis hotspots",
            start,
            end,
        )
    factors = {
        (calibration.month, calibration.metric): calibration
        for calibration in regional_calibration_records()
    }
    counts = defaultdict(lambda: [0, 0, 0.0, 0.0, 0, 0])
    observations_query = FirmsDetection.objects.filter(
        acquired_at__gte=datetime.combine(start, day_time.min, tzinfo=timezone.utc),
        acquired_at__lt=datetime.combine(
            end + timedelta(days=1),
            day_time.min,
            tzinfo=timezone.utc,
        ),
        source__in=("MODIS_SP", "VIIRS_SNPP_SP"),
    )
    regional_filter = _calibration_scope_filter()
    regional_sources = (
        Q(source="MODIS_SP", attributes__satellite="Aqua")
        | Q(source="VIIRS_SNPP_SP", attributes__satellite="N")
    )
    if bounds is not None:
        south, north, west, east = bounds
        bounds_filter = Q(
            latitude__gte=south,
            latitude__lte=north,
            longitude__gte=west,
            longitude__lte=east,
        )
        in_bounds_cells = observations_query.filter(bounds_filter).values_list(
            "grid_cell",
            flat=True,
        ).distinct()
        in_bounds_parents = {
            _source_parent(cell, HARMONIZED_H3_RESOLUTION)
            for cell in in_bounds_cells
        }
        existing_hotspot_cells = Hotspot.objects.filter(
            is_automated=True,
            acquired_at__gte=datetime.combine(
                start,
                day_time.min,
                tzinfo=timezone.utc,
            ),
            acquired_at__lt=datetime.combine(
                end + timedelta(days=1),
                day_time.min,
                tzinfo=timezone.utc,
            ),
            latitude__gte=south,
            latitude__lte=north,
            longitude__gte=west,
            longitude__lte=east,
        ).exclude(grid_cell="")
        existing_parent_cells = {
            cell
            for cell in existing_hotspot_cells.values_list("grid_cell", flat=True)
            if h3.is_valid_cell(cell) and h3.get_resolution(cell) == HARMONIZED_H3_RESOLUTION
        }
        candidate_parents = in_bounds_parents | existing_parent_cells
        boundary_parents = {
            parent
            for parent in candidate_parents
            if not all(
                south <= latitude <= north and west <= longitude <= east
                for latitude, longitude in h3.cell_to_boundary(parent)
            )
        }
        boundary_children = {
            child
            for parent in boundary_parents
            for child in h3.cell_to_children(parent, H3_RESOLUTION)
        }
        observations_query = observations_query.filter(
            bounds_filter | Q(grid_cell__in=boundary_children)
        )
        source_cells = list(
            observations_query.values_list("grid_cell", flat=True).distinct()
        )
        replace_cells = set(source_cells)
        replace_cells.update(
            _source_parent(cell, HARMONIZED_H3_RESOLUTION)
            for cell in source_cells
        )
        replace_cells.update(boundary_parents)
        replace_cells = list(replace_cells)
    else:
        replace_cells = None

    def collect_observations(queryset, regional):
        observations = (
            queryset.annotate(
                acquired_date=TruncDate("acquired_at", tzinfo=timezone.utc)
            )
            .values("acquired_date", "grid_cell", "source", "daynight")
            .annotate(count=Count("id"), frp_sum=Sum("frp"), frp_count=Count("frp"))
            .order_by()
            .iterator(chunk_size=5000)
        )
        for row in observations:
            day = row["acquired_date"]
            index = 0 if row["source"] == "MODIS_SP" else 1
            cell = _source_parent(row["grid_cell"], HARMONIZED_H3_RESOLUTION)
            values = counts[(day, cell, row["daynight"], regional)]
            values[index] += row["count"]
            values[index + 2] += row["frp_sum"] or 0.0
            values[index + 4] += row["frp_count"]

    collect_observations(
        observations_query.filter(regional_filter).filter(regional_sources),
        regional=True,
    )
    collect_observations(
        observations_query.exclude(regional_filter).filter(
            Q(source="MODIS_SP", attributes__satellite="Aqua")
        ),
        regional=False,
    )

    hotspots_query = Hotspot.objects.filter(
        is_automated=True,
        acquired_at__gte=datetime.combine(start, day_time.min, tzinfo=timezone.utc),
        acquired_at__lt=datetime.combine(
            end + timedelta(days=1),
            day_time.min,
            tzinfo=timezone.utc,
        ),
    )
    if bounds is not None:
        hotspots_query = hotspots_query.filter(
            Q(
                latitude__gte=south,
                latitude__lte=north,
                longitude__gte=west,
                longitude__lte=east,
            )
            | Q(grid_cell__in=replace_cells)
        )

    cell_groups = defaultdict(list)
    for (day, cell, daynight, regional), values in counts.items():
        cell_groups[(day, cell)].append((regional, daynight, values))

    output = []
    for (day, cell), groups in cell_groups.items():
        harmonized_count = 0.0
        max_harmonized_count = 0.0
        frp_values = []
        methods = set()
        contributing_sensors = set()
        contributing_regions = set()
        extrapolated = False
        for is_regional, daynight, values in groups:
            modis_count, viirs_count, modis_frp, viirs_frp, modis_frp_n, viirs_frp_n = values
            aqua_on, snpp_on = sensors_operating(day)
            count_calibration = factors.get((day.month, "count")) if is_regional else None
            frp_calibration = factors.get((day.month, "frp")) if is_regional else None
            count_calibrated = _calibration_factor_is_usable(count_calibration)

            # Outside the geographic scope, keep the Aqua-only series.
            use_modis = aqua_on and modis_count > 0
            use_viirs = snpp_on and count_calibrated and viirs_count > 0
            if not use_modis and not use_viirs:
                continue

            # An unknown turn cannot establish a pair. Prefer Aqua when available.
            if use_modis and daynight not in ("D", "N"):
                use_viirs = False
            modis = Observation.from_detection(modis_count, aqua_on)
            viirs = Observation.from_detection(viirs_count if use_viirs else 0, snpp_on)
            count_factor = count_calibration.factor if count_calibrated else 1.0
            harmonized_count += fuse_observations(modis, viirs, count_factor)
            methods.add(
                "fused" if use_modis and use_viirs
                else "calibrated" if use_viirs
                else "observed"
            )
            max_harmonized_count += max(
                modis_count if use_modis else 0,
                count_factor * viirs_count if use_viirs else 0,
            )
            contributing_regions.add(is_regional)
            if use_modis:
                contributing_sensors.add("MODIS-Aqua")
            if use_viirs:
                contributing_sensors.add("VIIRS-SNPP")
                extrapolated |= bool(
                    day.year < CALIBRATION_FIRST_YEAR or day.year > CALIBRATION_LAST_YEAR
                    or count_calibration.overlap_start and day.year < count_calibration.overlap_start.year
                    or count_calibration.overlap_end and day.year > count_calibration.overlap_end.year
                )

            complete_frp = (
                is_regional
                and (not use_modis or modis_frp_n == modis_count)
                and (not use_viirs or (
                    viirs_frp_n == viirs_count and _calibration_factor_is_usable(frp_calibration)
                ))
            )
            if not complete_frp:
                frp_values.append(None)
            elif use_modis and use_viirs:
                frp_values.append((modis_frp + viirs_frp * frp_calibration.factor) / 2)
            elif use_viirs:
                frp_values.append(viirs_frp * frp_calibration.factor)
            else:
                frp_values.append(modis_frp)

        if not methods:
            continue
        harmonized_frp = sum(frp_values) if all(value is not None for value in frp_values) else None
        estimate_kind = (
            "extrapolated" if extrapolated
            else next(iter(methods)) if len(methods) == 1 and len(contributing_regions) == 1
            else "mixed"
        )
        confidence = (
            "partial-calibration" if len(contributing_regions) > 1 and "VIIRS-SNPP" in contributing_sensors
            else "regional-calibrated" if "VIIRS-SNPP" in contributing_sensors
            else "aqua-basis"
        )
        sensor = "+".join(sorted(contributing_sensors))
        latitude, longitude = h3.cell_to_latlng(cell)
        acquired_at = datetime.combine(day, day_time.min, tzinfo=timezone.utc)
        fingerprint = hashlib.sha256(f"harmonized|{day.isoformat()}|{cell}".encode()).hexdigest()
        output.append(
            Hotspot(
                latitude=Decimal(str(latitude)).quantize(Decimal("0.00001")),
                longitude=Decimal(str(longitude)).quantize(Decimal("0.00001")),
                acquired_at=acquired_at,
                sensor=sensor,
                confidence=confidence,
                harmonized_count=harmonized_count,
                max_harmonized_count=max_harmonized_count,
                harmonized_frp=harmonized_frp,
                grid_cell=cell,
                is_automated=True,
                estimate_kind=estimate_kind,
                fingerprint=fingerprint,
            )
        )

    hotspots_query.delete()
    if output:
        Hotspot.objects.bulk_create(output, batch_size=2000)
    logger.info("Harmonização %s..%s: %s células-dia", start, end, len(output))
    return len(output)


def harmonize_range(start, end, chunk_days=5, bounds=None):
    if chunk_days < 1 or start > end:
        raise ValueError("Intervalo de harmonização inválido.")
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=chunk_days - 1), end)
        harmonize_window(cursor, chunk_end, bounds=bounds)
        cursor = chunk_end + timedelta(days=1)
