import os
import sqlite3
from datetime import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand

from api.models import FirmsPipelineState, Hotspot


class Command(BaseCommand):
    help = "Copia hotspots da base SQLite usada pela versão anterior para o PostgreSQL."

    def handle(self, *args, **options):
        state, _ = FirmsPipelineState.objects.get_or_create(pk=1)
        if state.legacy_data_migrated:
            self.stdout.write("Migração da base SQLite anterior já concluída.")
            return
        legacy_path = "/legacy_data/fire.sqlite3"
        if not os.path.exists(legacy_path):
            self.stdout.write("Nenhuma base SQLite anterior encontrada.")
            state.legacy_data_migrated = True
            state.save(update_fields=["legacy_data_migrated", "updated_at"])
            return

        with sqlite3.connect(f"file:{legacy_path}?mode=ro", uri=True) as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            if "api_hotspot" not in tables:
                self.stdout.write("A base SQLite anterior não contém hotspots.")
                state.legacy_data_migrated = True
                state.save(update_fields=["legacy_data_migrated", "updated_at"])
                return

            cursor = connection.execute(
                "SELECT latitude, longitude, acquired_at, sensor, confidence, frp, fingerprint "
                "FROM api_hotspot"
            )
            batch = []
            migrated = 0
            for latitude, longitude, acquired_at, sensor, confidence, frp, fingerprint in cursor:
                batch.append(
                    Hotspot(
                        latitude=Decimal(latitude),
                        longitude=Decimal(longitude),
                        acquired_at=datetime.fromisoformat(acquired_at),
                        sensor=sensor,
                        confidence=confidence,
                        frp=frp,
                        fingerprint=fingerprint,
                    )
                )
                if len(batch) == 2000:
                    Hotspot.objects.bulk_create(batch, batch_size=2000, ignore_conflicts=True)
                    migrated += len(batch)
                    batch.clear()
            if batch:
                Hotspot.objects.bulk_create(batch, batch_size=2000, ignore_conflicts=True)
                migrated += len(batch)

        state.legacy_data_migrated = True
        state.save(update_fields=["legacy_data_migrated", "updated_at"])
        self.stdout.write(f"Registros SQLite copiados/verificados: {migrated}.")
