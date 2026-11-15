from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("api", "0005_limit_backfill_to_five_years")]

    operations = [
        migrations.AddField(
            model_name="firmsarearequest",
            name="download_sources",
            field=models.BooleanField(default=True),
        ),
    ]
