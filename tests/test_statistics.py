"""Tests for the assembled deck statistics."""

import pytest

from mtg_deck_analyzer.domain.statistics import curve_bars, deck_statistics


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
    def test_the_library_excludes_the_commander(self):
        assert deck_statistics(_deck())["library_size"] == 99

    def test_lands_are_counted(self):
        assert deck_statistics(_deck())["land_count"] == 38

    def test_an_empty_deck_does_not_explode(self):
        stats = deck_statistics([])
        assert stats["library_size"] == 0
        assert stats["fixing"] == []


class TestCurve:
    def test_the_curve_has_one_entry_per_bucket(self):
        curve = deck_statistics(_deck())["curve"]
        assert [entry["label"] for entry in curve] == [
            "0", "1", "2", "3", "4", "5", "6", "7+"
        ]

    def test_lands_stay_off_the_curve(self):
        curve = deck_statistics(_deck())["curve"]
        assert curve[0]["count"] == 0
        assert curve[2]["count"] == 51
        assert curve[3]["count"] == 11  # 10 Divination + the commander


class TestSourcesKnown:
    def test_a_freshly_analyzed_deck_knows_its_sources(self):
        assert deck_statistics(_deck())["sources_known"] is True

    def test_a_deck_stored_before_produced_mana_does_not(self):
        old = [{"quantity": 38, "is_commander": False,
                "data": _card("Forest", "Basic Land — Forest")}]
        stats = deck_statistics(old)
        assert stats["sources_known"] is False
        assert stats["sources"]["G"] == 0


class TestRoles:
    def test_roles_are_labelled_and_ordered(self):
        from mtg_deck_analyzer.domain.constants import ROLE_ORDER

        roles = deck_statistics(_deck())["roles"]
        assert [entry["key"] for entry in roles] == ROLE_ORDER
        assert roles[0]["label"] == "Ramp"

    def test_the_draw_role_is_counted(self):
        roles = {e["key"]: e for e in deck_statistics(_deck())["roles"]}
        assert roles["draw"]["count"] == 10


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

    def test_role_odds_rise_with_every_draw_step(self):
        hand = deck_statistics(_deck())["opening_hand"]
        draw = next(entry for entry in hand["roles"] if entry["key"] == "draw")
        odds = {entry["turn"]: entry["p"] for entry in draw["odds"]}
        assert draw["count"] == 10
        assert odds[1] == pytest.approx(0.5372, abs=1e-4)
        assert odds[3] == pytest.approx(0.6328, abs=1e-4)
        assert odds[5] == pytest.approx(0.7103, abs=1e-4)

    def test_a_role_the_deck_does_not_play_is_never_drawn(self):
        hand = deck_statistics(_deck())["opening_hand"]
        tutor = next(entry for entry in hand["roles"] if entry["key"] == "tutor")
        assert tutor["count"] == 0
        assert all(entry["p"] == 0.0 for entry in tutor["odds"])


class TestCurveBars:
    def test_the_tallest_bucket_is_full_height(self):
        bars = curve_bars([{"label": "1", "count": 4}, {"label": "2", "count": 8}])
        assert bars[1]["pct"] == 100
        assert bars[0]["pct"] == 50

    def test_an_empty_curve_has_no_division_by_zero(self):
        bars = curve_bars([{"label": "1", "count": 0}])
        assert bars[0]["pct"] == 0
