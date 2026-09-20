"""The statistics checked against a real Moxfield deck's published figures.

Moxfield shows these numbers for deck h5DS-VylIUuNFYmbtXS4uQ. They were not
chosen to make our code pass, which is what makes them worth testing against:
a synthetic fixture can be bent to fit a bug, an external one cannot.
"""

import json
from pathlib import Path

import pytest

from mtg_deck_analyzer.domain.mana import land_production, mana_value_summary
from mtg_deck_analyzer.domain.statistics import deck_statistics

DECK = json.loads(
    (Path(__file__).parent / "fixtures" / "moxfield_reference_deck.json").read_text()
)


class TestManaValues:
    def test_the_published_totals_and_averages(self):
        mv = mana_value_summary(DECK)
        assert mv["total"] == 156
        assert mv["average"] == pytest.approx(1.59, abs=0.005)
        assert mv["average_without_lands"] == pytest.approx(2.11, abs=0.005)
        assert mv["median"] == 1
        assert mv["median_without_lands"] == 2


class TestLands:
    def test_modal_cards_with_a_land_back_are_counted(self):
        out = land_production(DECK)
        assert out["lands"] == 27
        assert out["symbol_slots"] == 49


class TestColors:
    def _colors(self):
        return {c["key"]: c for c in deck_statistics(DECK)["colors"]}

    @pytest.mark.parametrize(
        "color,production,on_lands",
        [("W", 37, 20), ("U", 52, 29), ("B", 19, 10),
         ("R", 41, 22), ("G", 19, 10), ("C", 15, 8)],
    )
    def test_production_and_land_share_match_moxfield(self, color, production,
                                                       on_lands):
        entry = self._colors()[color]
        assert entry["production_pct"] == production
        assert entry["lands_pct"] == on_lands

    def test_the_symbol_share_matches_moxfield(self):
        assert self._colors()["W"]["symbol_pct"] == 21

    def test_the_blue_sparkline_dips_at_six_and_returns_at_seven(self):
        # The signature that confirmed what the sparkline plots.
        assert self._colors()["U"]["curve"] == [1, 9, 6, 11, 7, 2, 0, 1]


class TestCurve:
    def test_the_curve_totals_match_the_published_chart(self):
        curve = deck_statistics(DECK)["curve"]
        totals = [b["permanents"] + b["spells"] for b in curve]
        assert totals == [8, 24, 11, 20, 7, 3, 0, 1]

    def test_the_curve_covers_every_non_land_card(self):
        curve = deck_statistics(DECK)["curve"]
        assert sum(b["permanents"] + b["spells"] for b in curve) == 74
