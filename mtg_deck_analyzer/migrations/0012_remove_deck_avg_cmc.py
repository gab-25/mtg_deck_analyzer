from django.db import migrations


class Migration(migrations.Migration):
    """Drops ``Deck.avg_cmc``, which the statistics panel made redundant.

    The mana curve replaced the only reader of this column. The PDF fact sheet
    still prints an average, but computes it from the deck's cards rather than
    reading it back, so nothing depends on the stored value.
    """

    dependencies = [
        ("mtg_deck_analyzer", "0011_deck_statistics"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="deck",
            name="avg_cmc",
        ),
    ]
