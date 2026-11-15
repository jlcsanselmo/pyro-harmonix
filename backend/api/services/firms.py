import csv
import hashlib
import io
import logging
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime, time as day_time, timedelta, timezone
from decimal import Decimal, DecimalException

import h3
from django.db import transaction
from django.db.models import Count
from django.db.models.functions import ExtractMonth

from api.models import FirmsDetection, Hotspot, SensorCalibration

logger = logging.getLogger(__name__)

FIRMS_API = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
BRAZIL_AREA = "-74,-34,-34,6"
MAX_DAYS_PER_REQUEST = 5
MAX_RESPONSE_BYTES = 200 * 1024 * 1024
REQUEST_DELAY_SECONDS = 3
H3_RESOLUTION = 8
HISTORY_YEARS = 5
MIN_CALIBRATION_DETECTIONS = 500
SOURCES = (
    ("MODIS_SP", date(2000, 11, 1)),
    ("VIIRS_SNPP_SP", date(2012, 1, 20)),
)


class FirmsError(Exception):
    pass


class FirmsResponseTooLarge(FirmsError):
    pass


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
    else:
        acquired_time = datetime.strptime(raw_time.zfill(4), "%H%M").time()
    return datetime.combine(acquired_date, acquired_time, tzinfo=timezone.utc)


def iter_firms_csv(content, source):
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        raise FirmsError("A resposta da FIRMS não contém cabeçalho CSV.")

    fields = [field.strip().lower() for field in reader.fieldnames]
    required = {"latitude", "longitude", "acq_date", "acq_time"}
    if not required.issubset(fields):
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
        unique[fingerprint] = FirmsDetection(
            source=source,
            latitude=latitude,
            longitude=longitude,
            acquired_at=acquired_at,
            grid_cell=cell,
            confidence=row.get("confidence", "")[:32],
            frp=frp,
            daynight=row.get("daynight", "")[:1],
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
        content = body.decode("utf-8-sig")
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

    batch = []
    received = 0
    for detection in iter_firms_csv(content, source):
        batch.append(detection)
        if len(batch) == 2000:
            _upsert_detections(batch)
            received += len(batch)
            batch.clear()
    if batch:
        _upsert_detections(batch)
        received += len(batch)
    logger.info("FIRMS %s %s..%s (%s): %s registros recebidos", source, start, end, area, received)
    return received


def _upsert_detections(rows):
    with transaction.atomic():
        FirmsDetection.objects.bulk_create(
            rows,
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


def calculate_calibration():
    overlap_end = datetime.now(timezone.utc).date()
    overlap_start = history_start_date(overlap_end)
    overlap = FirmsDetection.objects.filter(
        acquired_at__gte=datetime.combine(overlap_start, day_time.min, tzinfo=timezone.utc),
        acquired_at__lt=datetime.combine(
            overlap_end + timedelta(days=1),
            day_time.min,
            tzinfo=timezone.utc,
        ),
        latitude__gte=-34,
        latitude__lte=6,
        longitude__gte=-74,
        longitude__lte=-34,
    )
    totals = {}
    for source in ("MODIS_SP", "VIIRS_SNPP_SP"):
        monthly = (
            overlap.filter(source=source)
            .annotate(month=ExtractMonth("acquired_at"))
            .values("month")
            .annotate(count=Count("id"))
        )
        totals[source] = {row["month"]: row["count"] for row in monthly}

    for month in range(1, 13):
        modis_count = totals["MODIS_SP"].get(month, 0)
        viirs_count = totals["VIIRS_SNPP_SP"].get(month, 0)
        calibrated = (
            modis_count >= MIN_CALIBRATION_DETECTIONS
            and viirs_count >= MIN_CALIBRATION_DETECTIONS
        )
        factor = modis_count / viirs_count if calibrated else 1.0
        SensorCalibration.objects.update_or_create(
            month=month,
            defaults={
                "factor": factor,
                "modis_detections": modis_count,
                "viirs_detections": viirs_count,
                "overlap_start": overlap_start,
                "overlap_end": overlap_end,
                "calibrated": calibrated,
            },
        )


def harmonize_window(start, end):
    factors = {
        calibration.month: calibration
        for calibration in SensorCalibration.objects.all()
    }
    counts = defaultdict(lambda: [0, 0])
    observations = (
        FirmsDetection.objects.filter(
            acquired_at__gte=datetime.combine(start, day_time.min, tzinfo=timezone.utc),
            acquired_at__lt=datetime.combine(
                end + timedelta(days=1),
                day_time.min,
                tzinfo=timezone.utc,
            ),
            source__in=("MODIS_SP", "VIIRS_SNPP_SP"),
        )
        .values("acquired_at__date", "grid_cell", "source")
        .annotate(count=Count("id"))
        .order_by()
        .iterator(chunk_size=5000)
    )
    for row in observations:
        day = row["acquired_at__date"]
        index = 0 if row["source"] == "MODIS_SP" else 1
        counts[(day, row["grid_cell"])][index] = row["count"]

    Hotspot.objects.filter(
        is_automated=True,
        acquired_at__gte=datetime.combine(start, day_time.min, tzinfo=timezone.utc),
        acquired_at__lt=datetime.combine(
            end + timedelta(days=1),
            day_time.min,
            tzinfo=timezone.utc,
        ),
    ).delete()

    output = []
    for (day, cell), (modis_count, viirs_count) in counts.items():
        calibration = factors.get(day.month)
        factor = calibration.factor if calibration and calibration.calibrated else 1.0
        adjusted_viirs = viirs_count * factor
        if modis_count and adjusted_viirs:
            harmonized_count = (modis_count + adjusted_viirs) / 2
        else:
            harmonized_count = float(modis_count or adjusted_viirs)
        latitude, longitude = h3.cell_to_latlng(cell)
        acquired_at = datetime.combine(day, day_time.min, tzinfo=timezone.utc)
        fingerprint = hashlib.sha256(f"harmonized|{day.isoformat()}|{cell}".encode()).hexdigest()
        output.append(
            Hotspot(
                latitude=Decimal(str(latitude)).quantize(Decimal("0.00001")),
                longitude=Decimal(str(longitude)).quantize(Decimal("0.00001")),
                acquired_at=acquired_at,
                sensor="MODIS+VIIRS-SNPP",
                confidence="calibrated" if calibration and calibration.calibrated else "uncalibrated",
                harmonized_count=harmonized_count,
                grid_cell=cell,
                is_automated=True,
                fingerprint=fingerprint,
            )
        )

    if output:
        Hotspot.objects.bulk_create(output, batch_size=2000)
    logger.info("Harmonização %s..%s: %s células-dia", start, end, len(output))
    return len(output)


def harmonize_range(start, end, chunk_days=5):
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=chunk_days - 1), end)
        harmonize_window(cursor, chunk_end)
        cursor = chunk_end + timedelta(days=1)
