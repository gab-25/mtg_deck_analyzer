from django.db import migrations, models


class Migration(migrations.Migration):
    """Adds the Commander format a deck is built for.

    Existing decks inherit the column default, ``commander``, which is exactly
    what they were: the format only became a choice here. Nothing is
    re-validated — ``Deck.cards`` is a snapshot taken at analysis time, and
    "Re-analyze" re-runs the check.
    """

    dependencies = [
        ("mtg_deck_analyzer", "0006_commander_format"),
    ]

    operations = [
        migrations.AddField(
            model_name="deck",
            name="format",
            field=models.CharField(
                choices=[("commander", "Commander"), ("duel", "Duel Commander")],
                default="commander",
                max_length=16,
            ),
        ),
    ]
