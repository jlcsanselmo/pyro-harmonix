from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("api", "0009_hotspot_estimate_kind")]

    operations = [
        migrations.CreateModel(
            name="FirmsDownload",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source", models.CharField(max_length=32)),
                ("start_date", models.DateField()),
                ("end_date", models.DateField()),
                ("area", models.CharField(max_length=128)),
                ("sha256", models.CharField(max_length=64)),
                ("received_rows", models.PositiveIntegerField()),
                ("archived", models.BooleanField(default=False)),
                ("fetched_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "constraints": [models.UniqueConstraint(
                    fields=("source", "start_date", "end_date", "area", "sha256"),
                    name="api_firms_download_identity",
                )],
            },
        ),
    ]
