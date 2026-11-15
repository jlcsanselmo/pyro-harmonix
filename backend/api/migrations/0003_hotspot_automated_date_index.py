from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("api", "0002_firms_pipeline")]

    operations = [
        migrations.AddIndex(
            model_name="hotspot",
            index=models.Index(
                fields=["is_automated", "acquired_at"],
                name="api_hot_auto_date_idx",
            ),
        ),
    ]
