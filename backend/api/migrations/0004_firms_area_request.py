from datetime import date

from django.db import migrations, models


def restart_brazil_backfill(apps, schema_editor):
    checkpoint_model = apps.get_model("api", "FirmsCheckpoint")
    for source, first_day in (
        ("MODIS_SP", date(2000, 11, 1)),
        ("VIIRS_SNPP_SP", date(2012, 1, 20)),
    ):
        checkpoint_model.objects.update_or_create(
            source=source,
            defaults={"next_date": first_day},
        )

    state_model = apps.get_model("api", "FirmsPipelineState")
    state_model.objects.filter(pk=1).update(
        initial_backfill_complete=False,
        last_sync_at=None,
        status="waiting_for_key",
    )


class Migration(migrations.Migration):
    dependencies = [("api", "0003_hotspot_automated_date_index")]

    operations = [
        migrations.CreateModel(
            name="FirmsAreaRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(default="queued", max_length=16)),
                ("south", models.DecimalField(decimal_places=4, max_digits=8)),
                ("north", models.DecimalField(decimal_places=4, max_digits=8)),
                ("west", models.DecimalField(decimal_places=4, max_digits=8)),
                ("east", models.DecimalField(decimal_places=4, max_digits=8)),
                ("start_date", models.DateField()),
                ("end_date", models.DateField()),
                ("next_date", models.DateField()),
                ("last_error", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["created_at"]},
        ),
        migrations.RunPython(restart_brazil_backfill, migrations.RunPython.noop),
    ]
