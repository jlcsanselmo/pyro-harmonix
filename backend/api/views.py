import csv
import hashlib
import io
import json
import statistics
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.db.models import Count, Max, Min, Sum
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.utils.dateparse import parse_date
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import FirmsAreaRequest, FirmsCheckpoint, FirmsPipelineState, Hotspot
from .services.firms import history_start_date

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_UPLOAD_ROWS = 200_000
MAP_POINT_LIMIT = 10_000
AREA_REQUEST_LIMIT = 5
AREA_REQUEST_MAX_DAYS = 5 * 366
AREA_REQUEST_MAX_SPAN_DEGREES = Decimal("20")


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
        "grid_cell": row.grid_cell,
    }


def _csv_safe_text(value):
    text = str(value or "")
    return f"'{text}" if text.startswith(("=", "+", "-", "@", "\t", "\r")) else text


@require_GET
def health(request):
    return JsonResponse({"status": "ok"})


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
    return {
        "id": row.pk,
        "status": row.status,
        "south": str(row.south),
        "north": str(row.north),
        "west": str(row.west),
        "east": str(row.east),
        "start": row.start_date.isoformat(),
        "end": row.end_date.isoformat(),
        "next_date": row.next_date.isoformat(),
        "last_error": row.last_error,
    }


@require_GET
def area_requests(request):
    return JsonResponse(
        {"requests": [_area_request_data(row) for row in FirmsAreaRequest.objects.order_by("-created_at")[:5]]}
    )


@csrf_exempt
@require_POST
def create_area_request(request):
    try:
        payload = json.loads(request.body)
        start = parse_date(payload.get("start", ""))
        end = parse_date(payload.get("end", ""))
        south, north, west, east = [
            Decimal(str(payload.get(name, "")))
            for name in ("south", "north", "west", "east")
        ]
    except (json.JSONDecodeError, UnicodeDecodeError, AttributeError, InvalidOperation, TypeError):
        return _json_error("Informe datas e coordenadas válidas.")

    if not start or not end or start > end:
        return _json_error("Informe um intervalo de datas válido.")
    if start < history_start_date():
        return _json_error("A coleta FIRMS está limitada aos últimos cinco anos.")
    if end > datetime.now(timezone.utc).date():
        return _json_error("A data final não pode ser futura.")
    if (end - start).days + 1 > AREA_REQUEST_MAX_DAYS:
        return _json_error("Cada solicitação pode abranger no máximo cinco anos.")
    if not all(value.is_finite() for value in (south, north, west, east)):
        return _json_error("As coordenadas devem ser números finitos.")
    if south < -90 or north > 90 or south >= north:
        return _json_error("A latitude deve estar entre -90 e 90, com sul menor que norte.")
    if west < -180 or east > 180 or west >= east:
        return _json_error("A longitude deve estar entre -180 e 180, com oeste menor que leste.")
    if (
        north - south > AREA_REQUEST_MAX_SPAN_DEGREES
        or east - west > AREA_REQUEST_MAX_SPAN_DEGREES
    ):
        return _json_error("A área deve ter no máximo 20° de largura e 20° de altura.")
    if FirmsAreaRequest.objects.filter(status__in=("queued", "downloading")).count() >= AREA_REQUEST_LIMIT:
        return _json_error("A fila está cheia. Tente novamente quando uma solicitação terminar.", 429)

    area_request = FirmsAreaRequest.objects.create(
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
    total = rows.aggregate(count=Sum("harmonized_count"))["count"] or 0
    points = [_point_data(row) for row in rows[:limit]]
    return JsonResponse({"total": total, "returned": len(points), "limit": limit, "points": points})


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
                "acq_datetime",
                "sensor",
                "confidence",
                "frp",
                "harmonized_count",
                "grid_cell",
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
                    row.harmonized_count,
                    row.grid_cell,
                ]
            )
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate(0)

    response.streaming_content = csv_rows()
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
    years = {
        year: [0] * 12
        for year in range(start.year, end.year + 1)
    } if area_first_date else {}
    for entry in month_counts:
        year = entry["acquired_at__year"]
        month = entry["acquired_at__month"]
        years.setdefault(year, [0] * 12)[month - 1] = entry["count"]

    monthly_totals = [0] * 12
    for entry in month_counts:
        monthly_totals[entry["acquired_at__month"] - 1] += entry["count"]

    totals = selected.aggregate(first=Min("acquired_at"), last=Max("acquired_at"))
    comparison_start_day = (
        start.day if start.year == end.year and start.month == end.month else 1
    )
    end_month_observed = selected.filter(
        acquired_at__year=end.year,
        acquired_at__month=end.month,
        acquired_at__day__gte=comparison_start_day,
        acquired_at__day__lte=end.day,
    ).aggregate(count=Sum("harmonized_count"))["count"] or 0

    baseline_values = []
    first_date = area_first_date
    if first_date:
        historical_start = datetime(first_date.year, 1, 1, tzinfo=timezone.utc)
        historical_end = datetime(end.year, 1, 1, tzinfo=timezone.utc)
        historical_rows = (
            area.filter(
                acquired_at__gte=historical_start,
                acquired_at__lt=historical_end,
                acquired_at__month=end.month,
                acquired_at__day__gte=comparison_start_day,
                acquired_at__day__lte=end.day,
            )
            .values("acquired_at__year", "acquired_at__month")
            .annotate(count=Sum("harmonized_count"))
        )
        historical_counts = {
            entry["acquired_at__year"]: entry["count"]
            for entry in historical_rows
        }
        baseline_values = [
            historical_counts.get(year, 0)
            for year in range(first_date.year, end.year)
        ]

    historical_median = statistics.median(baseline_values) if baseline_values else None
    anomaly_percent = None
    if historical_median is not None:
        if historical_median:
            anomaly_percent = round((end_month_observed - historical_median) / historical_median * 100, 1)
        else:
            anomaly_percent = 0 if end_month_observed == 0 else None

    return JsonResponse(
        {
            "total": selected.aggregate(count=Sum("harmonized_count"))["count"] or 0,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "monthly_totals": monthly_totals,
            "years": [
                {"year": year, "months": counts, "total": sum(counts)}
                for year, counts in sorted(years.items())
            ],
            "comparison": {
                "month": end.month,
                "year": end.year,
                "observed": end_month_observed,
                "historical_median": historical_median,
                "anomaly_percent": anomaly_percent,
                "historical_years": len(baseline_values),
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
    sensor = row.get("sensor", "").strip() or "unknown"
    confidence = row.get("confidence", "").strip()
    identity = "|".join(
        [
            str(latitude.quantize(Decimal("0.00001"))),
            str(longitude.quantize(Decimal("0.00001"))),
            acquired_at.isoformat(),
            sensor,
            confidence,
            frp_text,
        ]
    )
    return Hotspot(
        latitude=latitude,
        longitude=longitude,
        acquired_at=acquired_at,
        sensor=sensor[:80],
        confidence=confidence[:32],
        frp=frp,
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
    writer.writerow(["latitude", "longitude", "acq_datetime", "sensor", "confidence", "frp"])
    return response
