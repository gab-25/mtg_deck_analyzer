from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("mtg_deck_analyzer", "0010_backfill_legacy_deck_versions"),
    ]

    operations = [
        migrations.AddField(
            model_name="deck",
            name="statistics",
            field=models.JSONField(default=dict),
        ),
    ]
