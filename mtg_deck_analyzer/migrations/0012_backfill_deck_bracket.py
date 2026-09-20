from django.db import migrations

from mtg_deck_analyzer.domain.bracket import estimate_bracket


def backfill_bracket(apps, schema_editor):
    """Fills in the bracket for decks analyzed before the estimate existed.

    ``estimate_bracket`` is pure and ``Deck.cards`` already holds every card,
    so no re-analysis and no network call is needed. Those cards were
    processed before ``game_changer`` was carried through, so the signal comes
    from the fallback name list: this backfill is exactly as good as that list.
    """
    Deck = apps.get_model("mtg_deck_analyzer", "Deck")
    for deck in Deck.objects.exclude(cards=[]).iterator():
        deck.bracket = estimate_bracket(deck.cards)
        deck.save(update_fields=["bracket"])


class Migration(migrations.Migration):
    dependencies = [("mtg_deck_analyzer", "0011_deck_bracket")]

    operations = [
        migrations.RunPython(backfill_bracket, migrations.RunPython.noop),
    ]
