from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count, Max, Min, Q

import h3

from api.models import FirmsDetection, Hotspot
from api.services.firms import HARMONIZED_H3_RESOLUTION, H3_RESOLUTION, harmonize_range


def _parse_bounds(value):
    try:
        south, north, west, east = (
            Decimal(part.strip()) for part in value.split(",")
        )
    except (InvalidOperation, ValueError):
        raise CommandError("--bounds must be S,N,W,E decimal coordinates.") from None
    if (
        not all(coordinate.is_finite() for coordinate in (south, north, west, east))
        or not -90 <= south < north <= 90
        or not -180 <= west < east <= 180
    ):
        raise CommandError("--bounds must be valid, increasing geographic bounds.")
    return south, north, west, east


class Command(BaseCommand):
    help = "Rebuild stored harmonized hotspots from FirmsDetection records."

    def add_arguments(self, parser):
        parser.add_argument("--start", type=date.fromisoformat)
        parser.add_argument("--end", type=date.fromisoformat)
        parser.add_argument("--bounds", help="Area bounds in S,N,W,E order.")
        parser.add_argument(
            "--purge-automated",
            action="store_true",
            help="Delete existing automated hotspots in the selected window first.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        date_range = FirmsDetection.objects.aggregate(
            first=Min("acquired_at"),
            last=Max("acquired_at"),
        )
        if date_range["first"] is None:
            raise CommandError("No FirmsDetection records are available to rebuild.")

        start = options["start"] or date_range["first"].date()
        end = options["end"] or date_range["last"].date()
        if start > end:
            raise CommandError("--start must not be later than --end.")
        bounds = _parse_bounds(options["bounds"]) if options["bounds"] else None
        window_start = datetime.combine(start, time.min, tzinfo=timezone.utc)
        window_end = datetime.combine(
            end + timedelta(days=1),
            time.min,
            tzinfo=timezone.utc,
        )

        if options["purge_automated"]:
            purge = Hotspot.objects.filter(
                is_automated=True,
                acquired_at__gte=window_start,
                acquired_at__lt=window_end,
            )
            if bounds is not None:
                south, north, west, east = bounds
                purge = purge.filter(
                    latitude__gte=south,
                    latitude__lte=north,
                    longitude__gte=west,
                    longitude__lte=east,
                )
            deleted = purge.delete()[0]
            self.stdout.write(f"Purged {deleted} automated hotspots.")

        harmonize_range(start, end, chunk_days=5, bounds=bounds)
        summary = Hotspot.objects.filter(
            is_automated=True,
            acquired_at__gte=window_start,
            acquired_at__lt=window_end,
        )
        if bounds is not None:
            south, north, west, east = bounds
            bounds_filter = Q(
                latitude__gte=south,
                latitude__lte=north,
                longitude__gte=west,
                longitude__lte=east,
            )
            detection_cells = FirmsDetection.objects.filter(
                acquired_at__gte=window_start,
                acquired_at__lt=window_end,
                source__in=("MODIS_SP", "VIIRS_SNPP_SP"),
                latitude__gte=south,
                latitude__lte=north,
                longitude__gte=west,
                longitude__lte=east,
            ).values_list("grid_cell", flat=True)
            parent_cells = {
                h3.cell_to_parent(cell, HARMONIZED_H3_RESOLUTION)
                for cell in detection_cells
                if h3.get_resolution(cell) == H3_RESOLUTION
            }
            summary = summary.filter(bounds_filter | Q(grid_cell__in=parent_cells))
        confidence_counts = summary.values("confidence").annotate(count=Count("id"))
        self.stdout.write(f"Harmonized confidence summary for {start}..{end}:")
        for row in confidence_counts.order_by("confidence"):
            self.stdout.write(f"  {row['confidence'] or '(blank)'}: {row['count']}")
