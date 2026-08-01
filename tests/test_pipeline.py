"""Tests for the analysis pipeline's Commander gatekeeping (no network)."""

import pytest

from mtg_deck_analyzer import pipeline

COMMANDER = "Atraxa, Praetors' Voice"


def _fake_card(name):
    """Scryfall-shaped data for any name, tuned to keep a deck legal."""
    if name == COMMANDER:
        type_line = "Legendary Creature — Phyrexian Angel Horror"
    elif name == "Forest":
        type_line = "Basic Land — Forest"
    else:
        type_line = "Creature — Elf Druid"
    return {
        "name": name,
        "type_line": type_line,
        "cmc": 2.0,
        "price_eur": 0.10,
        "color_identity": ["G"],
        "image_paths": [],
        "faces": [{"name": name, "mana_cost": "{G}", "type_line": type_line,
                   "rules_text": ""}],
    }


@pytest.fixture
def fetched(monkeypatch):
    """Resolves every card locally; ``fetched.missing`` names never resolve."""

    class Fetcher:
        missing = set()

        def __call__(self, name, cache):
            return None if name in self.missing else _fake_card(name)

    fetcher = Fetcher()
    monkeypatch.setattr(pipeline, "fetch_card_data", fetcher)
    return fetcher


def _decklist(spells=60, forests=39, commander_line=f"1 {COMMANDER}"):
    lines = ["Commander", commander_line, "", "Deck"]
    lines += [f"1 Spell {i}" for i in range(spells)]
    lines.append(f"{forests} Forest")
    return "\n".join(lines)


def _analyze(decklist):
    return pipeline.analyze_decklist(decklist, cache=object(), skip_analysis=True)


def test_a_legal_deck_produces_commander_stats(fetched):
    result = _analyze(_decklist())

    stats = result["stats"]
    assert stats["commanders"] == [COMMANDER]
    assert stats["color_identity"] == ["G"]
    assert stats["total_cards"] == 100
    # The commander flag survives all the way to the stored cards.
    assert result["processed_cards"][0]["is_commander"] is True


def test_rejects_a_deck_that_breaks_the_commander_rules(fetched):
    with pytest.raises(ValueError) as excinfo:
        _analyze(_decklist(forests=30))  # 91 cards

    message = str(excinfo.value)
    assert "not a legal Commander deck" in message
    assert "91 cards" in message


def test_rejects_a_deck_without_a_commander(fetched):
    decklist = "\n".join(
        [f"1 Spell {i}" for i in range(61)] + ["39 Forest"]
    )
    with pytest.raises(ValueError, match="No commander declared"):
        _analyze(decklist)


def test_names_the_cards_that_could_not_be_found(fetched):
    fetched.missing = {"Spell 7"}

    with pytest.raises(ValueError) as excinfo:
        _analyze(_decklist())

    message = str(excinfo.value)
    assert "could not be found on Scryfall" in message
    assert "Spell 7" in message
    # The missing card must not be reported as a size problem instead.
    assert "99 cards" not in message


def test_empty_decklist_is_rejected(fetched):
    with pytest.raises(ValueError, match="No cards could be parsed"):
        _analyze("   \n// nothing here\n")
