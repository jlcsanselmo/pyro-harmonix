import gzip
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from api.services.firms import FirmsError, _upsert_detections, iter_firms_csv

SAMPLE_SOURCES = {"MODIS_SP", "VIIRS_SNPP_SP"}


class Command(BaseCommand):
    help = "Load compressed FIRMS CSV samples without contacting NASA."

    def add_arguments(self, parser):
        parser.add_argument("--path", default="docs/data/raw")

    @transaction.atomic
    def handle(self, *args, **options):
        sample_path = Path(options["path"])
        files = sorted(sample_path.glob("*.csv.gz"))
        if not files:
            raise CommandError(f"No .csv.gz sample files found in {sample_path}.")

        loaded = 0
        for path in files:
            source = path.name.rsplit("_", 1)[0]
            if source not in SAMPLE_SOURCES:
                raise CommandError(f"Unsupported sample source in filename: {path.name}")
            try:
                with gzip.open(path, "rt", encoding="utf-8", newline="") as sample_file:
                    content = sample_file.read()
                batch = []
                file_count = 0
                for detection in iter_firms_csv(content, source):
                    batch.append(detection)
                    if len(batch) == 2000:
                        _upsert_detections(batch)
                        file_count += len(batch)
                        batch.clear()
                if batch:
                    _upsert_detections(batch)
                    file_count += len(batch)
            except (OSError, UnicodeDecodeError, FirmsError) as error:
                raise CommandError(f"Could not load {path}: {error}") from error
            loaded += file_count
            self.stdout.write(f"Loaded {file_count} records from {path}.")
        self.stdout.write(f"Processed {loaded} regional FIRMS records.")
