"""The management command that refills stored statistics after a schema bump.

Statistics are computed when a deck is analyzed and never on the way out, so
a bump of STATISTICS_SCHEMA leaves every stored blob stale until this command
runs. It is the deploy step that a bump costs.
"""

from io import StringIO

import pytest
from django.core.management import call_command

from mtg_deck_analyzer.domain.statistics import STATISTICS_SCHEMA, deck_statistics
from mtg_deck_analyzer.models import Deck


def _cards():
    return [
        {"quantity": 1, "is_commander": True,
         "data": {"name": "Cmdr", "type_line": "Legendary Creature — Human",
                  "cmc": 3.0, "color_identity": ["W"], "produced_mana": [],
                  "faces": [{"name": "Cmdr", "mana_cost": "{2}{W}",
                             "type_line": "Legendary Creature — Human",
                             "rules_text": ""}]}},
        {"quantity": 40, "is_commander": False,
         "data": {"name": "Plains", "type_line": "Basic Land — Plains",
                  "cmc": 0.0, "color_identity": [], "produced_mana": ["W"],
                  "faces": [{"name": "Plains", "mana_cost": "",
                             "type_line": "Basic Land — Plains",
                             "rules_text": ""}]}},
    ]


def _run(*args):
    out = StringIO()
    call_command("recompute_statistics", *args, stdout=out)
    return out.getvalue()


@pytest.mark.django_db
class TestRecomputeStatistics:
    def test_a_stale_blob_is_replaced_with_the_current_shape(self):
        deck = Deck.objects.create(name="Stale", raw_decklist="", cards=_cards(),
                                   statistics={"schema": 1, "curve": "nonsense"})

        _run()

        deck.refresh_from_db()
        assert deck.statistics == deck_statistics(_cards())

    def test_a_missing_blob_is_filled_in(self):
        deck = Deck.objects.create(name="Empty", raw_decklist="", cards=_cards(),
                                   statistics={})

        _run()

        deck.refresh_from_db()
        assert deck.statistics["schema"] == STATISTICS_SCHEMA

    def test_a_current_blob_is_left_alone(self):
        # Marked so a rewrite would show: the command must not touch a deck
        # whose blob already carries the current schema.
        current = {**deck_statistics(_cards()), "library_size": 999}
        deck = Deck.objects.create(name="Current", raw_decklist="", cards=_cards(),
                                   statistics=current)

        _run()

        deck.refresh_from_db()
        assert deck.statistics["library_size"] == 999

    def test_all_forces_a_current_blob_to_be_recomputed(self):
        current = {**deck_statistics(_cards()), "library_size": 999}
        deck = Deck.objects.create(name="Current", raw_decklist="", cards=_cards(),
                                   statistics=current)

        _run("--all")

        deck.refresh_from_db()
        assert deck.statistics == deck_statistics(_cards())

    def test_a_deck_with_no_cards_is_skipped(self):
        # Nothing to compute from: an analysis that never finished, or one
        # that failed. Writing an empty-deck blob would make the page show a
        # panel of zeroes where it currently shows none.
        deck = Deck.objects.create(name="No cards", raw_decklist="", cards=[],
                                   statistics={})

        _run()

        deck.refresh_from_db()
        assert deck.statistics == {}

    def test_it_reports_how_many_decks_it_rewrote(self):
        Deck.objects.create(name="Stale", raw_decklist="", cards=_cards(),
                            statistics={"schema": 1})
        Deck.objects.create(name="Current", raw_decklist="", cards=_cards(),
                            statistics=deck_statistics(_cards()))

        assert "1" in _run()


@pytest.mark.django_db
class TestBackfillMigration:
    """The one-off backfill, which is the same work as the command.

    It runs against an empty database in the test suite, so it is exercised
    here against rows instead.
    """

    def test_a_stale_deck_is_filled_in(self):
        from importlib import import_module

        from django.apps import apps as django_apps

        module = import_module(
            "mtg_deck_analyzer.migrations.0013_backfill_deck_statistics"
        )
        deck = Deck.objects.create(name="Stale", raw_decklist="", cards=_cards(),
                                   statistics={"schema": 1})

        module.backfill(django_apps, None)

        deck.refresh_from_db()
        assert deck.statistics == deck_statistics(_cards())
