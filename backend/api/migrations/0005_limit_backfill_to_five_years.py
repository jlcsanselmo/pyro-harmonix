from datetime import date, datetime, timezone

from django.db import migrations


def restart_recent_backfill(apps, schema_editor):
    today = datetime.now(timezone.utc).date()
    try:
        window_start = today.replace(year=today.year - 5)
    except ValueError:
        window_start = today.replace(year=today.year - 5, day=28)

    checkpoint_model = apps.get_model("api", "FirmsCheckpoint")
    for source, product_start in (
        ("MODIS_SP", date(2000, 11, 1)),
        ("VIIRS_SNPP_SP", date(2012, 1, 20)),
    ):
        checkpoint_model.objects.update_or_create(
            source=source,
            defaults={"next_date": max(product_start, window_start)},
        )

    state_model = apps.get_model("api", "FirmsPipelineState")
    state_model.objects.filter(pk=1).update(
        initial_backfill_complete=False,
        last_sync_at=None,
        status="waiting_for_key",
    )


class Migration(migrations.Migration):
    dependencies = [("api", "0004_firms_area_request")]

    operations = [
        migrations.RunPython(restart_recent_backfill, migrations.RunPython.noop),
    ]
