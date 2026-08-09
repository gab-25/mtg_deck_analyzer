from django.db import migrations, models


class Migration(migrations.Migration):
    """Commander-only refactor: the format is fixed, so ``deck_type`` goes away
    and the commander identity / legality of the deck take its place."""

    dependencies = [
        ("mtg_deck_analyzer", "0005_purge_non_english_cache"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="deck",
            name="deck_type",
        ),
        migrations.AddField(
            model_name="deck",
            name="commanders",
            field=models.JSONField(default=list),
        ),
        migrations.AddField(
            model_name="deck",
            name="color_identity",
            field=models.JSONField(default=list),
        ),
    ]
