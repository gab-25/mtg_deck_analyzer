"""Tests for the assembled deck statistics."""

import pytest

from mtg_deck_analyzer.domain.statistics import (
    STATISTICS_SCHEMA,
    curve_bars,
    deck_statistics,
)


def _card(name, type_line, *, mana_cost="", text="", cmc=0.0, produced=None):
    data = {
        "name": name,
        "type_line": type_line,
        "cmc": cmc,
        "faces": [{"name": name, "mana_cost": mana_cost, "type_line": type_line,
                   "rules_text": text}],
    }
    if produced is not None:
        data["produced_mana"] = produced
    return data


def _deck():
    """A legal-shaped deck: a commander plus a 99-card library, 38 of them lands."""
    return [
        {"quantity": 1, "is_commander": True,
         "data": _card("Commander", "Legendary Creature — Elf",
                       mana_cost="{2}{G}", cmc=3.0)},
        {"quantity": 38, "is_commander": False,
         "data": _card("Forest", "Basic Land — Forest",
                       text="{T}: Add {G}.", produced=["G"])},
        {"quantity": 10, "is_commander": False,
         "data": _card("Divination", "Sorcery", mana_cost="{2}{U}", cmc=3.0,
                       text="Draw two cards.", produced=[])},
        {"quantity": 51, "is_commander": False,
         "data": _card("Grizzly Bears", "Creature — Bear", mana_cost="{1}{G}",
                       cmc=2.0, text="", produced=[])},
    ]


class TestShape:
    def test_it_carries_its_schema_version(self):
        assert deck_statistics(_deck())["schema"] == STATISTICS_SCHEMA

    def test_the_top_level_keys_are_the_contract(self):
        assert set(deck_statistics(_deck())) == {
            "schema", "library_size", "land_count", "sources_known", "curve",
            "mana_values", "colors", "opening_hand",
        }

    def test_an_empty_deck_does_not_explode(self):
        stats = deck_statistics([])
        assert stats["library_size"] == 0
        assert stats["mana_values"]["total"] == 0


class TestLibraryAndLands:
    def test_the_library_excludes_the_commander(self):
        assert deck_statistics(_deck())["library_size"] == 99

    def test_lands_are_counted(self):
        assert deck_statistics(_deck())["land_count"] == 38


class TestColorsBlock:
    def test_every_color_is_present_in_wubrg_order_then_colorless(self):
        keys = [c["key"] for c in deck_statistics(_deck())["colors"]]
        assert keys == ["W", "U", "B", "R", "G", "C"]

    def test_colorless_has_no_card_or_symbol_share(self):
        # Colourless is a production column only: it has no colour identity
        # and no coloured pips, so those two figures stay at zero.
        colorless = deck_statistics(_deck())["colors"][-1]
        assert colorless["card_pct"] == 0
        assert colorless["symbol_pct"] == 0

    def test_a_colors_curve_has_one_entry_per_bucket(self):
        for entry in deck_statistics(_deck())["colors"]:
            assert len(entry["curve"]) == 8

    def test_green_gets_its_share_of_the_symbols(self):
        # 52 of the deck's 62 colored pips are green (commander + Grizzly
        # Bears); deck_pips must actually be wired in for this to be nonzero.
        green = next(c for c in deck_statistics(_deck())["colors"] if c["key"] == "G")
        assert green["symbol_pct"] == round(52 / 62 * 100)

    def test_green_lands_cover_the_whole_mana_base(self):
        green = next(c for c in deck_statistics(_deck())["colors"] if c["key"] == "G")
        assert green["production_pct"] == 100
        assert green["lands_pct"] == 100


class TestSourcesKnown:
    def _legacy_deck(self):
        """A deck analyzed before produced_mana was carried through.

        None of its cards carry the key at all, which is exactly what a deck
        analyzed before that field was stored looks like.
        """
        return [
            {"quantity": 1, "is_commander": True,
             "data": _card("Commander", "Legendary Creature — Elf",
                           mana_cost="{2}{G}", cmc=3.0)},
            {"quantity": 38, "is_commander": False,
             "data": _card("Forest", "Basic Land — Forest",
                           text="{T}: Add {G}.")},
            {"quantity": 61, "is_commander": False,
             "data": _card("Grizzly Bears", "Creature — Bear",
                           mana_cost="{1}{G}", cmc=2.0)},
        ]

    def test_it_is_false_when_no_card_carries_produced_mana(self):
        assert deck_statistics(self._legacy_deck())["sources_known"] is False

    def test_it_is_true_once_at_least_one_card_carries_it(self):
        assert deck_statistics(_deck())["sources_known"] is True


class TestCurve:
    def test_the_curve_has_one_entry_per_bucket(self):
        curve = deck_statistics(_deck())["curve"]
        assert [entry["label"] for entry in curve] == [
            "0", "1", "2", "3", "4", "5", "6", "7+"
        ]

    def test_lands_stay_off_the_curve(self):
        curve = deck_statistics(_deck())["curve"]
        assert curve[0]["permanents"] == 0
        assert curve[0]["spells"] == 0
        assert curve[2]["permanents"] == 51  # 51 Grizzly Bears, a creature
        assert curve[3]["spells"] == 10  # 10 Divination; the commander is excluded


class TestRemovedBlocks:
    """Fixing, role tagging and the old top-level sources/pips figures are gone."""

    def test_the_statistics_carry_no_fixing_roles_or_legacy_source_keys(self):
        stats = deck_statistics(_deck())
        for gone in ("fixing", "roles", "baseline", "pips", "sources"):
            assert gone not in stats

    def test_the_opening_hand_carries_no_role_odds(self):
        assert "roles" not in deck_statistics(_deck())["opening_hand"]


class TestOpeningHand:
    def test_land_counts_match_the_hypergeometric(self):
        hand = deck_statistics(_deck())["opening_hand"]
        odds = {entry["lands"]: entry["p"] for entry in hand["land_counts"]}
        assert odds[2] == pytest.approx(0.2809, abs=1e-4)
        assert odds[3] == pytest.approx(0.2957, abs=1e-4)
        assert odds[4] == pytest.approx(0.1785, abs=1e-4)
        assert odds[5] == pytest.approx(0.0617, abs=1e-4)

    def test_keepable_is_two_to_five_lands(self):
        hand = deck_statistics(_deck())["opening_hand"]
        assert hand["keepable"] == pytest.approx(0.8168, abs=1e-4)

    def test_land_drops_get_harder_every_turn(self):
        hand = deck_statistics(_deck())["opening_hand"]
        drops = {entry["turn"]: entry["p"] for entry in hand["land_drops"]}
        assert drops[1] == pytest.approx(0.9707, abs=1e-4)
        assert drops[3] == pytest.approx(0.7482, abs=1e-4)
        assert drops[5] == pytest.approx(0.4202, abs=1e-4)


class TestCurveBars:
    def test_the_tallest_bucket_is_full_height(self):
        bars = curve_bars([
            {"label": "1", "permanents": 4, "spells": 0},
            {"label": "2", "permanents": 5, "spells": 3},
        ])
        assert bars[1]["pct"] == 100
        assert bars[0]["pct"] == 50

    def test_an_empty_curve_has_no_division_by_zero(self):
        bars = curve_bars([{"label": "1", "permanents": 0, "spells": 0}])
        assert bars[0]["pct"] == 0
