"""Fills in the statistics of decks analyzed before the current schema.

The statistics are computed when a deck is analyzed and never on the way out,
so a deck whose blob predates the current shape would show no panel at all.
This is the one-off backfill; ``manage.py recompute_statistics`` is the same
work, on demand, for the next bump.

The domain function is imported rather than frozen into this file: a copy of
it would be a hundred lines of duplicated arithmetic, and on a fresh database
this migration has no rows to touch.
"""

from django.db import migrations

from mtg_deck_analyzer.domain.statistics import STATISTICS_SCHEMA, deck_statistics


def backfill(apps, schema_editor):
    Deck = apps.get_model("mtg_deck_analyzer", "Deck")
    for deck in Deck.objects.iterator():
        cards = deck.cards or []
        # An analysis that never finished has nothing to compute from, and a
        # blob of zeroes would show a panel where there should be none.
        if not cards:
            continue
        if (deck.statistics or {}).get("schema") == STATISTICS_SCHEMA:
            continue
        deck.statistics = deck_statistics(cards)
        deck.save(update_fields=["statistics"])


class Migration(migrations.Migration):
    dependencies = [
        ("mtg_deck_analyzer", "0012_remove_deck_avg_cmc"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
