from django.db import migrations

from mtg_deck_analyzer.domain.bracket import estimate_bracket
from mtg_deck_analyzer.domain.constants import DEFAULT_FORMAT


def backfill_bracket(apps, schema_editor):
    """Fills in the bracket for decks analyzed before the estimate existed.

    ``estimate_bracket`` is pure and ``Deck.cards`` already holds every card,
    so no re-analysis and no network call is needed. Those cards were
    processed before ``game_changer`` was carried through, so the signal comes
    from the fallback name list: this backfill is exactly as good as that list.

    A deck's format decides whether it gets a verdict at all; a Duel Commander
    deck keeps the empty dict, since that format has no bracket system.
    """
    Deck = apps.get_model("mtg_deck_analyzer", "Deck")
    for deck in Deck.objects.exclude(cards=[]).iterator():
        deck.bracket = estimate_bracket(deck.cards, deck.format or DEFAULT_FORMAT)
        deck.save(update_fields=["bracket"])


class Migration(migrations.Migration):
    dependencies = [("mtg_deck_analyzer", "0011_deck_bracket")]

    operations = [
        migrations.RunPython(backfill_bracket, migrations.RunPython.noop),
    ]
