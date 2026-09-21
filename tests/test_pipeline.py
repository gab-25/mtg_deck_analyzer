"""Tests for the analysis pipeline's Commander gatekeeping (no network)."""

import pytest

from mtg_deck_analyzer import pipeline
from mtg_deck_analyzer.integrations import openrouter

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


def test_the_analysis_text_comes_from_openrouter(fetched, monkeypatch):
    """The whole path pipeline -> OpenRouter -> stored analysis, HTTP mocked."""

    class Response:
        status_code = 200
        text = ""

        @staticmethod
        def json():
            return {"choices": [{"message": {"content": "## Commander & Archetype"}}]}

    sent = {}

    def fake_post(url, **kwargs):
        sent.update(url=url, **kwargs)
        return Response()

    monkeypatch.setattr(openrouter.requests, "post", fake_post)

    result = pipeline.analyze_decklist(
        _decklist(), api_key="key-123", cache=object()
    )

    assert result["deck_analysis"] == "## Commander & Archetype"
    assert sent["url"] == openrouter.API_URL
    # The commander is named in the prompt the deck is analyzed with.
    assert COMMANDER in sent["json"]["messages"][0]["content"]


def test_without_an_api_key_the_deck_is_analyzed_without_the_strategy_section(
    fetched, monkeypatch
):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(
        openrouter.requests,
        "post",
        lambda *a, **kw: pytest.fail("no request may be sent without an API key"),
    )

    result = pipeline.analyze_decklist(_decklist(), cache=object())

    assert result["deck_analysis"] is None
    assert result["stats"]["total_cards"] == 100


def test_the_format_picks_the_ban_list(monkeypatch):
    """Sol Ring: legal in Commander, banned in Duel. Same deck, two verdicts."""

    def fetch(name, cache):
        card = _fake_card(name)
        if name == "Spell 0":
            card["name"] = "Sol Ring"
            card["legalities"] = {"commander": "legal", "duel": "banned"}
        return card

    monkeypatch.setattr(pipeline, "fetch_card_data", fetch)

    # The default format accepts the deck outright.
    pipeline.analyze_decklist(_decklist(), cache=object(), skip_analysis=True)

    with pytest.raises(ValueError) as excinfo:
        pipeline.analyze_decklist(
            _decklist(), cache=object(), skip_analysis=True, fmt="duel"
        )
    message = str(excinfo.value)
    assert "Duel Commander" in message
    assert "Sol Ring" in message


def test_the_pipeline_returns_deck_statistics(fetched):
    stats = _analyze(_decklist())["stats"]

    assert stats["statistics"]["library_size"] == 99
    assert stats["statistics"]["land_count"] == 39
    assert len(stats["statistics"]["curve"]) == 8


def test_stats_carry_the_bracket_verdict(fetched):
    bracket = _analyze(_decklist())["stats"]["bracket"]

    assert bracket["bracket"] == 2
    assert bracket["label"] == "Core"
    assert bracket["signals"]["game_changers"] == []


def test_a_duel_commander_deck_gets_no_bracket(fetched):
    """Duel Commander has no bracket system, so the pipeline stores no verdict."""
    decklist = f"1 {COMMANDER} *CMDR*\n" + "\n".join(
        [f"1 Elf {i}" for i in range(98)] + ["1 Forest"]
    )
    result = pipeline.analyze_decklist(
        decklist, skip_analysis=True, cache=object(), fmt="duel"
    )
    assert result["stats"]["bracket"] == {}
