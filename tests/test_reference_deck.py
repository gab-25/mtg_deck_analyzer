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

    @pytest.mark.parametrize("color,card_pct", [("W", 21), ("U", 47), ("R", 18)])
    def test_the_card_share_matches_moxfield(self, color, card_pct):
        # Blue and red were long a couple of points high here, because colour
        # identity was counting Pact of Negation as blue and Rograkh as red.
        # Both cost {0} and are coloured by an indicator; Moxfield reads the
        # printed cost, so neither counts.
        assert self._colors()[color]["card_pct"] == card_pct

    def test_the_blue_sparkline_dips_at_six_and_returns_at_seven(self):
        # The signature that confirmed what the sparkline plots. Bucket 0 is
        # empty for the same reason blue reads 47%: Pact of Negation sits at
        # mana value 0 and is not counted a blue card.
        assert self._colors()["U"]["curve"] == [0, 9, 6, 11, 7, 2, 0, 1]

    @pytest.mark.parametrize("color", ["B", "G"])
    def test_black_and_green_touch_no_cards_despite_producing_mana(self, color):
        # This deck is Jeskai: black and green have a nonzero production_pct
        # (rainbow lands can tap for them) but the deck plays no black or
        # green cards and asks for no black or green pips. A colour column
        # should not read as "used" on production alone.
        entry = self._colors()[color]
        assert entry["card_pct"] == 0
        assert entry["symbol_pct"] == 0


class TestCurve:
    def test_the_curve_totals_match_the_published_chart(self):
        # These were first pinned a card short in buckets 0 and 4 — the two
        # partners — because the chart was read as though the commander were
        # excluded, and the one-bar difference was written off as misreading a
        # screenshot. It was not: Moxfield counts the commander.
        curve = deck_statistics(DECK)["curve"]
        totals = [b["permanents"] + b["spells"] for b in curve]
        assert totals == [9, 24, 11, 20, 8, 3, 0, 1]

    def test_the_curve_covers_every_non_land_card_and_the_commanders(self):
        curve = deck_statistics(DECK)["curve"]
        assert sum(b["permanents"] + b["spells"] for b in curve) == 76


STORM = json.loads(
    (Path(__file__).parent / "fixtures" / "moxfield_storm_deck.json").read_text()
)


class TestSecondReferenceDeck:
    """A second deck, checked the same way — RogShai - Jeskai Storm Combo.

    One deck can be matched by a formula that is right for the wrong reason.
    This one was fetched after the formulas were settled, and it is what
    caught the opening-hand land count reading the front face: Moxfield's
    published average of 1.64 only comes out at 23 lands, the any-face count,
    where the front face gives 21 and 1.50.
    """

    def _colors(self):
        return {c["key"]: c for c in deck_statistics(STORM)["colors"]}

    def test_the_average_lands_in_hand_match_moxfield(self):
        stats = deck_statistics(STORM)
        assert stats["library_size"] == 98
        assert stats["land_count"] == 23
        assert stats["opening_hand"]["average_lands"] == pytest.approx(1.64, abs=0.005)

    @pytest.mark.parametrize(
        "color,production", [("W", 39), ("U", 48), ("B", 26), ("R", 48),
                             ("G", 26), ("C", 22)]
    )
    def test_the_production_percentages_match_moxfield(self, color, production):
        assert self._colors()[color]["production_pct"] == production

    @pytest.mark.parametrize(
        "color,on_lands", [("W", 19), ("U", 23), ("B", 13), ("R", 23),
                           ("G", 13), ("C", 10)]
    )
    def test_the_land_share_matches_moxfield(self, color, on_lands):
        # Black and green sat a point low until percentages started rounding
        # half-up: both land on exactly 12.5%, where Python's round() picks
        # the even number and Moxfield picks 13.
        assert self._colors()[color]["lands_pct"] == on_lands
