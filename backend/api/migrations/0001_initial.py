from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Hotspot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("latitude", models.DecimalField(decimal_places=5, max_digits=8)),
                ("longitude", models.DecimalField(decimal_places=5, max_digits=8)),
                ("acquired_at", models.DateTimeField()),
                ("sensor", models.CharField(default="unknown", max_length=80)),
                ("confidence", models.CharField(blank=True, max_length=32)),
                ("frp", models.FloatField(blank=True, null=True)),
                ("fingerprint", models.CharField(max_length=64, unique=True)),
            ],
            options={"ordering": ["-acquired_at"]},
        ),
        migrations.AddIndex(
            model_name="hotspot",
            index=models.Index(fields=["acquired_at"], name="api_hotspot_acquire_5c0617_idx"),
        ),
        migrations.AddIndex(
            model_name="hotspot",
            index=models.Index(fields=["latitude", "longitude"], name="api_hotspot_latitud_1e6fe0_idx"),
        ),
    ]
