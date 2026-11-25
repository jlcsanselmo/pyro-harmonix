import csv
import hashlib
import io
import json
import math
import statistics
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

import h3

from django.db import IntegrityError, transaction
from django.db.models import Count, Max, Min, Q, Sum
from django.db.models.functions import TruncDate
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.utils.dateparse import parse_date
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import (
    FirmsAreaRequest,
    FirmsCheckpoint,
    FirmsPipelineState,
    Hotspot,
    RegionalSensorCalibration,
)
from .services.firms import (
    AQUA_START,
    CALIBRATION_BOUNDS,
    CALIBRATION_METHOD,
    CALIBRATION_H3_RESOLUTION,
    CALIBRATION_FIRST_YEAR,
    CALIBRATION_LAST_YEAR,
    SERIES_METHOD,
    CALIBRATION_PAIR_MODE,
    CALIBRATION_SCOPE,
    CALIBRATION_SHRINKAGE_PRIOR_PAIRS,
    HARMONIZED_H3_RESOLUTION,
    SOURCES,
    _build_calibration_groups,
    _calibration_detection_queryset,
    _calibration_overlap_years,
    estimate_area_download,
    regional_calibration_records,
)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_UPLOAD_ROWS = 200_000
MAP_POINT_LIMIT = 10_000
AREA_REQUEST_LIMIT = 5
AREA_REQUEST_MAX_DAYS = 366
AREA_REQUEST_MAX_SPAN_DEGREES = Decimal("20")
MIN_MEDIAN_FOR_PERCENT = 30


class RequestError(ValueError):
    pass


def _filters(request):
    try:
        start = parse_date(request.GET.get("start", "2000-01-01"))
        end = parse_date(request.GET.get("end", datetime.now(timezone.utc).date().isoformat()))
        south = Decimal(request.GET.get("south", "-34"))
        north = Decimal(request.GET.get("north", "6"))
        west = Decimal(request.GET.get("west", "-74"))
        east = Decimal(request.GET.get("east", "-34"))
    except (InvalidOperation, TypeError):
        raise RequestError("Coordenadas inválidas. Informe números decimais.") from None

    if not start or not end:
        raise RequestError("As datas devem estar no formato AAAA-MM-DD.")
    if start > end:
        raise RequestError("A data inicial deve ser anterior à data final.")
    if not all(value.is_finite() for value in (south, north, west, east)):
        raise RequestError("As coordenadas devem ser números finitos.")
    if south < -90 or north > 90 or south >= north:
        raise RequestError("A latitude deve estar entre -90 e 90, com sul menor que norte.")
    if west < -180 or east > 180 or west >= east:
        raise RequestError("A longitude deve estar entre -180 e 180, com oeste menor que leste.")

    return start, end, south, north, west, east


def _json_error(message, status=400):
    return JsonResponse({"error": message}, status=status)


def _area_queryset(south, north, west, east):
    return Hotspot.objects.filter(
        latitude__gte=south,
        latitude__lte=north,
        longitude__gte=west,
        longitude__lte=east,
    )


def _date_queryset(queryset, start, end):
    start_at = datetime.combine(start, time.min, tzinfo=timezone.utc)
    end_at = datetime.combine(end, time.max, tzinfo=timezone.utc)
    return queryset.filter(acquired_at__gte=start_at, acquired_at__lte=end_at)


def _estimate_kind(row):
    return row.estimate_kind or ("legacy" if row.is_automated else "uploaded")


def _point_data(row):
    return {
        "id": row.id,
        "latitude": float(row.latitude),
        "longitude": float(row.longitude),
        "acquired_at": row.acquired_at.isoformat(),
        "sensor": row.sensor,
        "confidence": row.confidence,
        "frp": row.frp,
        "harmonized_count": row.harmonized_count,
        "max_harmonized_count": row.max_harmonized_count,
        "harmonized_frp": row.harmonized_frp,
        "grid_cell": row.grid_cell,
        "estimate_kind": _estimate_kind(row),
        "coverage_status": "unknown",
    }


def _percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    portion = position - lower
    return ordered[lower] * (1 - portion) + ordered[upper] * portion


def _csv_safe_text(value):
    text = str(value or "")
    return f"'{text}" if text.startswith(("=", "+", "-", "@", "\t", "\r")) else text


@require_GET
def health(request):
    return JsonResponse({"status": "ok"})


@require_GET
def calibration_summary(request):
    rows = regional_calibration_records()
    dates = [row for row in rows if row.overlap_start and row.overlap_end]
    snapshot_path = Path(__file__).parent / "data" / "regional_sensor_calibration.json"
    with snapshot_path.open(encoding="utf-8") as snapshot_file:
        snapshot = json.load(snapshot_file)
    recalculated = (
        RegionalSensorCalibration.objects.filter(scope=CALIBRATION_SCOPE).count()
        == 24
    )
    source = "recalculated" if recalculated else "snapshot"
    if recalculated:
        groups = _build_calibration_groups(_calibration_detection_queryset())
        pair_mode = CALIBRATION_PAIR_MODE
        overlap_years = _calibration_overlap_years(groups)
    else:
        pair_mode = snapshot.get("pair_mode", CALIBRATION_PAIR_MODE)
        overlap_years = snapshot.get("overlap_years", [])
    annual = {}
    for metric in ("count", "frp"):
        metric_rows = [row for row in rows if row.metric == metric]
        modis_measure = sum(row.modis_measure for row in metric_rows)
        viirs_measure = sum(row.viirs_measure for row in metric_rows)
        annual[metric] = {
            "factor": modis_measure / viirs_measure if viirs_measure else None,
            "sample_size": sum(row.sample_size for row in metric_rows),
            "modis_measure": modis_measure,
            "viirs_measure": viirs_measure,
        }
    return JsonResponse(
        {
            "scope": CALIBRATION_SCOPE,
            "scope_label": "Altinópolis–Pitangueiras · Cerrado/interior de SP",
            "h3_resolution": CALIBRATION_H3_RESOLUTION,
            "bounds": {
                "south": float(CALIBRATION_BOUNDS[0]),
                "north": float(CALIBRATION_BOUNDS[1]),
                "west": float(CALIBRATION_BOUNDS[2]),
                "east": float(CALIBRATION_BOUNDS[3]),
            },
            "source": source,
            "annual": annual,
            "assessment_start_year": CALIBRATION_FIRST_YEAR,
            "assessment_end_year": CALIBRATION_LAST_YEAR,
            "coverage_status": "unknown",
            "series_method": SERIES_METHOD,
            "calibration_method": CALIBRATION_METHOD,
            "zero_filled_is_historical": True,
            "pair_mode": pair_mode,
            "overlap_years": overlap_years,
            "shrinkage_prior_pairs": CALIBRATION_SHRINKAGE_PRIOR_PAIRS,
            "overlap_start": min((row.overlap_start for row in dates), default=None),
            "overlap_end": max((row.overlap_end for row in dates), default=None),
            "factors": [
                {
                    "month": row.month,
                    "metric": row.metric,
                    "factor": row.factor,
                    "sample_size": row.sample_size,
                    "modis_measure": row.modis_measure,
                    "viirs_measure": row.viirs_measure,
                    "ci_lower": row.ci_lower,
                    "ci_upper": row.ci_upper,
                    "fallback_level": row.fallback_level,
                    "calibrated": row.calibrated,
                }
                for row in rows
            ],
            "fusion": [
                {
                    "month": row.month,
                    "average": row.fusion_average,
                    "maximum": row.fusion_maximum,
                    "zero_filled_mean": row.fusion_zero_filled,
                    "union_parent_days": (
                        row.fusion_union_parent_days
                        if row.fusion_union_parent_days is not None
                        else None
                    ),
                    "parent_day_night_samples": row.fusion_parent_days,
                }
                for row in rows
                if row.metric == "count"
            ],
        }
    )


@require_GET
def ingestion_status(request):
    state = FirmsPipelineState.objects.filter(pk=1).first()
    checkpoints = [
        {"source": row.source, "next_date": row.next_date.isoformat()}
        for row in FirmsCheckpoint.objects.order_by("source")
    ]
    return JsonResponse(
        {
            "status": state.status if state else "waiting_for_key",
            "active_source": state.active_source if state else "",
            "initial_backfill_complete": state.initial_backfill_complete if state else False,
            "last_sync_at": state.last_sync_at.isoformat() if state and state.last_sync_at else None,
            "last_error": state.last_error if state else "",
            "sources": checkpoints,
        }
    )


def _area_request_data(row):
    estimate = (
        estimate_area_download(
            row.start_date,
            row.end_date,
            row.south,
            row.north,
            row.west,
            row.east,
        )
        if row.download_sources
        else None
    )
    return {
        "id": row.pk,
        "status": row.status,
        "mode": "download" if row.download_sources else "stored",
        "south": str(row.south),
        "north": str(row.north),
        "west": str(row.west),
        "east": str(row.east),
        "start": row.start_date.isoformat(),
        "end": row.end_date.isoformat(),
        "next_date": row.next_date.isoformat(),
        "last_error": row.last_error,
        "estimate": estimate,
    }


def _area_request_parameters(payload):
    if not hasattr(payload, "get"):
        raise RequestError("Informe datas e coordenadas válidas.")
    today = datetime.now(timezone.utc).date()
    year_value = payload.get("year")
    if year_value not in (None, ""):
        try:
            year_text = str(year_value).strip()
            if isinstance(year_value, bool) or not year_text.isdecimal():
                raise ValueError
            year = int(year_text)
        except (TypeError, ValueError):
            raise RequestError("Selecione um ano válido.") from None
        if year < SOURCES[0][1].year or year > today.year:
            raise RequestError(
                f"Escolha um ano entre {SOURCES[0][1].year} e {today.year}."
            )
        start = datetime(year, 1, 1).date()
        end = min(datetime(year, 12, 31).date(), today)
    else:
        try:
            start = parse_date(str(payload.get("start", "") or ""))
            end = parse_date(str(payload.get("end", "") or ""))
        except (TypeError, ValueError):
            raise RequestError("Informe um intervalo de datas válido.") from None
        if not start or not end or start > end:
            raise RequestError("Informe um intervalo de datas válido.")
        if start.year != end.year:
            raise RequestError("Cada solicitação deve abranger um único ano.")
        year = start.year
        if year < SOURCES[0][1].year or year > today.year:
            raise RequestError(
                f"Escolha um ano entre {SOURCES[0][1].year} e {today.year}."
            )

    start = max(start, SOURCES[0][1])
    if not start or not end or start > end:
        raise RequestError(
            f"Os dados MODIS começam em {SOURCES[0][1].isoformat()}."
        )
    if end > today:
        raise RequestError("A data final não pode ser futura.")
    if (end - start).days + 1 > AREA_REQUEST_MAX_DAYS:
        raise RequestError("Cada solicitação pode abranger no máximo um ano.")

    try:
        south, north, west, east = [
            Decimal(str(payload.get(name, "")))
            for name in ("south", "north", "west", "east")
        ]
    except (InvalidOperation, TypeError):
        raise RequestError("Informe datas e coordenadas válidas.") from None
    if not all(value.is_finite() for value in (south, north, west, east)):
        raise RequestError("As coordenadas devem ser números finitos.")
    if south < -90 or north > 90 or south >= north:
        raise RequestError("A latitude deve estar entre -90 e 90, com sul menor que norte.")
    if west < -180 or east > 180 or west >= east:
        raise RequestError("A longitude deve estar entre -180 e 180, com oeste menor que leste.")
    if (
        north - south > AREA_REQUEST_MAX_SPAN_DEGREES
        or east - west > AREA_REQUEST_MAX_SPAN_DEGREES
    ):
        raise RequestError("A área deve ter no máximo 20° de largura e 20° de altura.")
    return start, end, south, north, west, east


@require_GET
def area_requests(request):
    return JsonResponse(
        {"requests": [_area_request_data(row) for row in FirmsAreaRequest.objects.order_by("-created_at")[:5]]}
    )


@require_GET
def estimate_area_request(request):
    try:
        start, end, south, north, west, east = _area_request_parameters(request.GET)
    except RequestError as error:
        return _json_error(str(error))
    return JsonResponse(
        {
            "year": start.year,
            "start": start.isoformat(),
            "end": end.isoformat(),
            **estimate_area_download(start, end, south, north, west, east),
        }
    )


@csrf_exempt
@require_POST
def create_area_request(request):
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError, AttributeError, InvalidOperation, TypeError):
        return _json_error("Informe datas e coordenadas válidas.")
    if not isinstance(payload, dict):
        return _json_error("Informe datas e coordenadas válidas.")

    try:
        start, end, south, north, west, east = _area_request_parameters(payload)
    except RequestError as error:
        return _json_error(str(error))
    download_sources = payload.get("download_sources", True)
    if not isinstance(download_sources, bool):
        return _json_error("A opção de baixar novos dados deve ser verdadeira ou falsa.")
    if FirmsAreaRequest.objects.filter(
        status__in=("queued", "downloading", "harmonizing")
    ).count() >= AREA_REQUEST_LIMIT:
        return _json_error("A fila está cheia. Tente novamente quando uma solicitação terminar.", 429)

    area_request = FirmsAreaRequest.objects.create(
        download_sources=download_sources,
        south=south,
        north=north,
        west=west,
        east=east,
        start_date=start,
        end_date=end,
        next_date=start,
    )
    return JsonResponse(_area_request_data(area_request), status=202)


@require_GET
def hotspots(request):
    try:
        start, end, south, north, west, east = _filters(request)
        limit = min(max(int(request.GET.get("limit", "5000")), 1), MAP_POINT_LIMIT)
    except (RequestError, ValueError) as error:
        return _json_error(str(error))

    rows = _date_queryset(_area_queryset(south, north, west, east), start, end)
    totals = rows.aggregate(total=Sum("harmonized_count"), records=Count("id"))
    points = [_point_data(row) for row in rows.order_by("-acquired_at", "pk")[:limit]]
    return JsonResponse({
        **totals, "returned": len(points), "limit": limit, "points": points,
        "coverage_status": "unknown",
    })


@require_GET
def hotspots_csv(request):
    try:
        start, end, south, north, west, east = _filters(request)
    except RequestError as error:
        return _json_error(str(error))

    rows = _date_queryset(_area_queryset(south, north, west, east), start, end)
    response = StreamingHttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="hotspots.csv"'

    def csv_rows():
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "latitude",
                "longitude",
                "acquired_at",
                "sensor",
                "confidence",
                "frp",
                "harmonized_frp",
                "harmonized_count",
                "max_harmonized_count",
                "grid_cell",
                "h3_resolution",
                "estimate_kind",
                "coverage_status",
            ]
        )
        yield "\ufeff" + buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)
        for row in rows.iterator(chunk_size=2000):
            writer.writerow(
                [
                    row.latitude,
                    row.longitude,
                    row.acquired_at.isoformat(),
                    _csv_safe_text(row.sensor),
                    _csv_safe_text(row.confidence),
                    row.frp if row.frp is not None else "",
                    row.harmonized_frp if row.harmonized_frp is not None else "",
                    row.harmonized_count,
                    row.max_harmonized_count if row.max_harmonized_count is not None else "",
                    row.grid_cell,
                    h3.get_resolution(row.grid_cell) if h3.is_valid_cell(row.grid_cell) else "",
                    _estimate_kind(row),
                    "unknown",
                ]
            )
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate(0)

    response.streaming_content = csv_rows()
    return response


@require_GET
def calendar_csv(request):
    try:
        start, end, south, north, west, east = _filters(request)
    except RequestError as error:
        return _json_error(str(error))

    month_totals = {
        (row["acquired_at__year"], row["acquired_at__month"]): row["total"]
        for row in _date_queryset(
            _area_queryset(south, north, west, east),
            start,
            end,
        )
        .values("acquired_at__year", "acquired_at__month")
        .annotate(total=Sum("harmonized_count"))
    }
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="calendar.csv"'
    writer = csv.writer(response)
    writer.writerow(["year", "month", "total"])
    for year in range(start.year, end.year + 1):
        first_month = start.month if year == start.year else 1
        last_month = end.month if year == end.year else 12
        for month in range(first_month, last_month + 1):
            writer.writerow(
                [
                    year,
                    month,
                    month_totals.get((year, month), ""),
                ]
            )
    return response


@require_GET
def analytics(request):
    try:
        start, end, south, north, west, east = _filters(request)
    except RequestError as error:
        return _json_error(str(error))

    area = _area_queryset(south, north, west, east)
    selected = _date_queryset(area, start, end)
    month_counts = list(
        selected.values("acquired_at__year", "acquired_at__month")
        .annotate(count=Sum("harmonized_count"))
        .order_by("acquired_at__year", "acquired_at__month")
    )
    area_first_date = area.aggregate(first=Min("acquired_at"))["first"]
    years = {}
    for entry in month_counts:
        year = entry["acquired_at__year"]
        month = entry["acquired_at__month"]
        years.setdefault(year, [None] * 12)[month - 1] = entry["count"]

    monthly_totals = [None] * 12
    for entry in month_counts:
        index = entry["acquired_at__month"] - 1
        monthly_totals[index] = (monthly_totals[index] or 0) + entry["count"]

    totals = selected.aggregate(
        first=Min("acquired_at"), last=Max("acquired_at"), count=Sum("harmonized_count"),
    )
    comparison_start_day = (
        start.day if start.year == end.year and start.month == end.month else 1
    )
    series_counts = {
        "value": Sum("harmonized_count"),
        "legacy": Count("id", filter=Q(is_automated=True, estimate_kind="")),
        "current": Count("id", filter=Q(is_automated=True) & ~Q(estimate_kind="")),
        "uploaded": Count("id", filter=Q(is_automated=False)),
    }
    comparison_window = dict(
        acquired_at__month=end.month,
        acquired_at__day__gte=comparison_start_day,
        acquired_at__day__lte=end.day,
    )
    current = selected.filter(acquired_at__year=end.year, **comparison_window).aggregate(**series_counts)
    end_month_observed = current["value"]
    series = [key for key in ("legacy", "current", "uploaded") if current[key]]
    historical_counts = {}
    excluded_years = []
    first_date = area_first_date
    if first_date and len(series) == 1:
        historical_rows = area.filter(
            acquired_at__lt=datetime(end.year, 1, 1, tzinfo=timezone.utc),
            **comparison_window,
        ).values("acquired_at__year").annotate(**series_counts)
        for row in historical_rows:
            year = row["acquired_at__year"]
            if sum(bool(row[key]) for key in ("legacy", "current", "uploaded")) == 1 and row[series[0]]:
                historical_counts[year] = row["value"]
            else:
                excluded_years.append(year)
    baseline_values = list(historical_counts.values())

    historical_median = (
        statistics.median(baseline_values)
        if len(baseline_values) >= 2
        else None
    )
    anomaly_percent = None
    if historical_median is not None and historical_median >= MIN_MEDIAN_FOR_PERCENT and end_month_observed is not None:
        anomaly_percent = round(
            (end_month_observed - historical_median) / historical_median * 100,
            1,
        )
    anomaly_absolute = (
        end_month_observed - historical_median
        if historical_median is not None and end_month_observed is not None
        else None
    )
    percentile_rank = (
        100
        * sum(value <= end_month_observed for value in baseline_values)
        / len(baseline_values)
        if baseline_values and end_month_observed is not None
        else None
    )
    yearly_values = []
    if first_date:
        yearly_values = [
            {
                "year": year,
                "value": (
                    end_month_observed
                    if year == end.year
                    else historical_counts.get(year)
                ),
            }
            for year in range(first_date.year, end.year + 1)
        ]
    confidence_counts = {
        row["confidence"] or "uncalibrated": row["count"]
        for row in selected.order_by()
        .values("confidence")
        .annotate(count=Count("id"))
    }
    active_days = (
        selected.order_by()
        .annotate(active_day=TruncDate("acquired_at", tzinfo=timezone.utc))
        .values("active_day")
        .distinct()
        .count()
    )
    active_cells = selected.exclude(grid_cell="").values("grid_cell").distinct().count()

    return JsonResponse(
        {
            "total": totals["count"],
            "data_status": "records_present" if totals["count"] is not None else "no_records",
            "coverage_status": "unknown",
            "estimate_kinds": {
                (row["estimate_kind"] or ("legacy" if row["is_automated"] else "uploaded")): row["count"]
                for row in selected.order_by().values("estimate_kind", "is_automated").annotate(count=Count("id"))
            },
            "start": start.isoformat(),
            "end": end.isoformat(),
            "calibration_state": confidence_counts,
            "h3_resolution": HARMONIZED_H3_RESOLUTION,
            "harmonized_start": AQUA_START.isoformat(),
            "series_basis": "aqua_eq",
            "active_days": active_days,
            "active_cells": active_cells,
            "monthly_totals": monthly_totals,
            "years": [
                {
                    "year": year,
                    "months": counts,
                    "total": sum(count for count in counts if count is not None),
                }
                for year, counts in sorted(years.items())
            ],
            "comparison": {
                "month": end.month,
                "year": end.year,
                "observed": end_month_observed,
                "historical_median": historical_median,
                "anomaly_percent": anomaly_percent,
                "historical_years": len(baseline_values),
                "excluded_years": sorted(excluded_years),
                "mixed_current_methods": len(series) > 1,
                "ratio_to_historical_max": (
                    end_month_observed / max(baseline_values)
                    if end_month_observed is not None and baseline_values and max(baseline_values) > 0
                    else None
                ),
                "yearly_values": yearly_values,
                "percentile_rank": percentile_rank,
                "historical_min": min(baseline_values) if baseline_values else None,
                "historical_max": max(baseline_values) if baseline_values else None,
                "p25": _percentile(baseline_values, 0.25),
                "p75": _percentile(baseline_values, 0.75),
                "anomaly_absolute": anomaly_absolute,
                "anomaly_reliable": (
                    historical_median is not None
                    and historical_median >= MIN_MEDIAN_FOR_PERCENT
                ),
            },
            "first_observation": totals["first"].date().isoformat() if totals["first"] else None,
            "last_observation": totals["last"].date().isoformat() if totals["last"] else None,
        }
    )


def _parse_hotspot(row, line_number):
    latitude = Decimal(row.get("latitude") or "")
    longitude = Decimal(row.get("longitude") or "")
    if not latitude.is_finite() or not longitude.is_finite():
        raise RequestError(f"Linha {line_number}: latitude e longitude devem ser valores finitos.")
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise RequestError(f"Linha {line_number}: coordenadas fora dos limites geográficos.")

    acquired_text = row.get("acq_datetime", "")
    if acquired_text:
        acquired_at = datetime.fromisoformat(acquired_text.strip().replace("Z", "+00:00"))
    else:
        acquired_date = row.get("acq_date", "").strip()
        acquired_time = row.get("acq_time", "00:00").strip() or "00:00"
        acquired_at = datetime.combine(
            datetime.fromisoformat(acquired_date).date(),
            time.fromisoformat(acquired_time),
        )
    if acquired_at.tzinfo is None:
        acquired_at = acquired_at.replace(tzinfo=timezone.utc)
    acquired_at = acquired_at.astimezone(timezone.utc)

    frp_text = row.get("frp", "").strip()
    frp = float(frp_text) if frp_text else None
    if frp is not None and (frp < 0 or frp != frp or frp == float("inf")):
        raise RequestError(f"Linha {line_number}: FRP deve ser um número finito não negativo.")
    count_text = row.get("harmonized_count", "").strip()
    harmonized_count = float(count_text) if count_text else 1
    if not math.isfinite(harmonized_count) or harmonized_count < 0:
        raise RequestError(
            f"Linha {line_number}: harmonized_count deve ser um número finito não negativo."
        )
    sensor = row.get("sensor", "").strip() or "unknown"
    confidence = row.get("confidence", "").strip()
    identity_parts = [
        str(latitude.quantize(Decimal("0.00001"))),
        str(longitude.quantize(Decimal("0.00001"))),
        acquired_at.isoformat(),
        sensor,
        confidence,
        frp_text,
    ]
    if harmonized_count != 1:
        identity_parts.append(repr(harmonized_count))
    identity = "|".join(identity_parts)
    return Hotspot(
        latitude=latitude,
        longitude=longitude,
        acquired_at=acquired_at,
        sensor=sensor[:80],
        confidence=confidence[:32],
        frp=frp,
        harmonized_count=harmonized_count,
        fingerprint=hashlib.sha256(identity.encode("utf-8")).hexdigest(),
    )


@csrf_exempt
@require_POST
def upload(request):
    uploaded_file = request.FILES.get("file")
    if not uploaded_file:
        return _json_error("Selecione um arquivo CSV para importar.")
    if uploaded_file.size > MAX_UPLOAD_BYTES:
        return _json_error("O arquivo excede o limite de 10 MB.")

    try:
        content = uploaded_file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        return _json_error("O CSV deve usar codificação UTF-8.")

    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        return _json_error("O arquivo CSV está vazio ou não contém cabeçalho.")
    if any(not name or not name.strip() for name in reader.fieldnames):
        return _json_error("O cabeçalho CSV contém uma coluna sem nome.")
    reader.fieldnames = [name.strip().lower() for name in reader.fieldnames]
    if len(set(reader.fieldnames)) != len(reader.fieldnames):
        return _json_error("O cabeçalho CSV contém nomes de coluna duplicados.")
    required = {"latitude", "longitude"}
    if not required.issubset(reader.fieldnames) or not (
        "acq_datetime" in reader.fieldnames or "acq_date" in reader.fieldnames
    ):
        return _json_error(
            "Cabeçalho inválido. Use latitude, longitude e acq_datetime "
            "(ou acq_date e, opcionalmente, acq_time)."
        )

    rows = []
    try:
        for line_number, row in enumerate(reader, start=2):
            if line_number - 1 > MAX_UPLOAD_ROWS:
                return _json_error("O arquivo excede o limite de 200.000 registros.")
            normalized = {key.strip().lower(): (value or "").strip() for key, value in row.items() if key}
            if not normalized.get("latitude") or not normalized.get("longitude"):
                raise RequestError(f"Linha {line_number}: latitude e longitude são obrigatórias.")
            rows.append(_parse_hotspot(normalized, line_number))
    except (ValueError, InvalidOperation, OverflowError) as error:
        if isinstance(error, RequestError):
            return _json_error(str(error))
        return _json_error(f"Não foi possível interpretar os dados da linha {line_number}: {error}")
    except csv.Error as error:
        return _json_error(f"CSV inválido: {error}")

    if not rows:
        return _json_error("O CSV não contém registros.")

    try:
        with transaction.atomic():
            before = Hotspot.objects.count()
            Hotspot.objects.bulk_create(rows, batch_size=2000, ignore_conflicts=True)
            inserted = Hotspot.objects.count() - before
    except IntegrityError:
        return _json_error("Não foi possível salvar os registros. Verifique os dados do arquivo.", 500)

    return JsonResponse(
        {"received": len(rows), "inserted": inserted, "duplicates": len(rows) - inserted},
        status=201,
    )


@require_GET
def template_csv(request):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="hotspots-template.csv"'
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(
        [
            "latitude",
            "longitude",
            "acq_datetime",
            "sensor",
            "confidence",
            "frp",
            "harmonized_count",
        ]
    )
    return response
