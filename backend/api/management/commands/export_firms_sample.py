import csv
import gzip
import io
import os
import tempfile
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from api.models import FirmsDetection
from api.services.firms import CALIBRATION_BOUNDS

REQUIRED_FIELDS = ("latitude", "longitude", "acq_date", "acq_time")
SAMPLE_PRODUCTS = {
    "MODIS_SP": "Aqua",
    "VIIRS_SNPP_SP": "N",
}


def _sample_queryset(source, year):
    south, north, west, east = CALIBRATION_BOUNDS
    return FirmsDetection.objects.filter(
        source=source,
        acquired_at__year=year,
        latitude__gte=south,
        latitude__lte=north,
        longitude__gte=west,
        longitude__lte=east,
        attributes__satellite=SAMPLE_PRODUCTS[source],
    ).order_by("acquired_at", "pk")


def _row_attributes(detection):
    values = dict(detection.attributes or {})
    acquired_at = detection.acquired_at
    values.setdefault("latitude", str(detection.latitude))
    values.setdefault("longitude", str(detection.longitude))
    values.setdefault("acq_date", acquired_at.date().isoformat())
    values.setdefault("acq_time", acquired_at.strftime("%H%M"))
    if detection.frp is not None:
        values.setdefault("frp", str(detection.frp))
    values.setdefault("daynight", detection.daynight)
    values.setdefault("confidence", detection.confidence)
    return values


class Command(BaseCommand):
    help = "Export regional MODIS-Aqua and VIIRS-SNPP source records as compressed CSV samples."

    def add_arguments(self, parser):
        parser.add_argument("--output-dir", default="docs/data/raw")
        parser.add_argument("--min-year", type=int, default=2002)
        parser.add_argument("--max-mb", type=float, default=8)

    def handle(self, *args, **options):
        output_dir = Path(options["output_dir"])
        min_year = options["min_year"]
        max_mb = options["max_mb"]
        if min_year < 2002:
            raise CommandError("--min-year must be 2002 or later.")
        if max_mb <= 0:
            raise CommandError("--max-mb must be greater than zero.")

        grouped = list(
            FirmsDetection.objects.filter(
                acquired_at__year__gte=min_year,
                source__in=SAMPLE_PRODUCTS,
            )
            .values("source", "acquired_at__year")
            .distinct()
            .order_by("source", "acquired_at__year")
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        temporary_outputs = []
        total_bytes = 0
        try:
            for entry in grouped:
                source = entry["source"]
                year = entry["acquired_at__year"]
                queryset = _sample_queryset(source, year)
                fieldnames = set(REQUIRED_FIELDS)
                for attributes in queryset.values_list("attributes", flat=True).iterator(
                    chunk_size=2000
                ):
                    fieldnames.update(attributes or {})
                if fieldnames == set(REQUIRED_FIELDS) and not queryset.exists():
                    continue
                fieldnames = sorted(fieldnames)
                filename = f"{source}_{year}.csv.gz"
                temporary = tempfile.NamedTemporaryFile(
                    prefix=f".{filename}.",
                    suffix=".tmp",
                    dir=output_dir,
                    delete=False,
                )
                temporary_path = Path(temporary.name)
                temporary.close()
                temporary_outputs.append(
                    (temporary_path, output_dir / filename)
                )
                with temporary_path.open("wb") as raw_file:
                    with gzip.GzipFile(
                        filename="",
                        mode="wb",
                        fileobj=raw_file,
                        mtime=0,
                    ) as compressed:
                        with io.TextIOWrapper(
                            compressed,
                            encoding="utf-8",
                            newline="",
                        ) as text_file:
                            writer = csv.DictWriter(
                                text_file,
                                fieldnames=fieldnames,
                                extrasaction="ignore",
                            )
                            writer.writeheader()
                            for detection in queryset.iterator(chunk_size=2000):
                                writer.writerow(_row_attributes(detection))
                total_bytes += temporary_path.stat().st_size

            total_mb = total_bytes / (1024 * 1024)
            self.stdout.write(f"Compressed sample size: {total_mb:.3f} MB.")
            if total_mb > max_mb:
                raise CommandError(
                    f"Sample exceeds --max-mb ({total_mb:.3f} MB > {max_mb:.3f} MB); "
                    "no output files were replaced."
                )
            for temporary_path, output_path in temporary_outputs:
                os.replace(temporary_path, output_path)
                self.stdout.write(f"Wrote {output_path}.")
            if not temporary_outputs:
                self.stdout.write("No eligible regional source detections found.")
        finally:
            for temporary_path, _ in temporary_outputs:
                if temporary_path.exists():
                    temporary_path.unlink()
