"""Tests for the OpenRouter deck-analysis client (no network)."""

import pytest
import requests

from mtg_deck_analyzer.integrations import openrouter

DECKLIST = "1 Atraxa, Praetors' Voice *CMDR*\n39 Forest"


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def _ok_payload(content="## Commander & Archetype\n- Good deck."):
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


@pytest.fixture
def posted(monkeypatch):
    """Captures the outgoing request; ``posted.response`` is what it returns."""

    class Poster:
        response = FakeResponse(_ok_payload())
        calls = []

        def __call__(self, url, **kwargs):
            self.calls.append({"url": url, **kwargs})
            if isinstance(self.response, Exception):
                raise self.response
            return self.response

        @property
        def call(self):
            return self.calls[-1]

    poster = Poster()
    monkeypatch.setattr(openrouter.requests, "post", poster)
    return poster


def test_posts_the_prompt_to_openrouter_and_returns_the_analysis(posted):
    result = openrouter.analyze_deck_list(
        DECKLIST, api_key="key-123", commanders=["Atraxa, Praetors' Voice"]
    )

    assert result == "## Commander & Archetype\n- Good deck."

    call = posted.call
    assert call["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert call["headers"]["Authorization"] == "Bearer key-123"
    # A hanging provider must not block the background analysis thread forever.
    assert call["timeout"]

    payload = call["json"]
    assert payload["model"] == "google/gemini-2.5-flash"
    assert len(payload["messages"]) == 1
    message = payload["messages"][0]
    assert message["role"] == "user"
    # The prompt carries the commander and the decklist.
    assert "Atraxa, Praetors' Voice" in message["content"]
    assert "39 Forest" in message["content"]


def test_the_model_can_be_changed_with_an_environment_variable(posted, monkeypatch):
    monkeypatch.setenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-4")

    openrouter.analyze_deck_list(DECKLIST, api_key="key-123")

    assert posted.call["json"]["model"] == "anthropic/claude-sonnet-4"


def test_falls_back_to_the_api_key_in_the_environment(posted, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "key-from-env")

    openrouter.analyze_deck_list(DECKLIST)

    assert posted.call["headers"]["Authorization"] == "Bearer key-from-env"


def test_without_an_api_key_nothing_is_sent_and_no_analysis_is_produced(
    posted, monkeypatch
):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    assert openrouter.analyze_deck_list(DECKLIST) is None
    assert posted.calls == []


def test_an_error_response_skips_the_analysis(posted):
    posted.response = FakeResponse({"error": {"message": "no credits"}}, status_code=402)

    assert openrouter.analyze_deck_list(DECKLIST, api_key="key-123") is None


def test_a_network_failure_skips_the_analysis(posted):
    posted.response = requests.RequestException("connection reset")

    assert openrouter.analyze_deck_list(DECKLIST, api_key="key-123") is None


def test_an_unexpected_payload_skips_the_analysis(posted):
    posted.response = FakeResponse({"choices": []})

    assert openrouter.analyze_deck_list(DECKLIST, api_key="key-123") is None


def test_an_empty_completion_skips_the_analysis(posted):
    posted.response = FakeResponse(_ok_payload(content="   "))

    assert openrouter.analyze_deck_list(DECKLIST, api_key="key-123") is None


def test_the_prompt_asks_the_model_to_infer_an_undeclared_commander(posted):
    openrouter.analyze_deck_list(DECKLIST, api_key="key-123", commanders=[])

    assert "infer the most likely one" in posted.call["json"]["messages"][0]["content"]


def test_log_analysis_unavailable_explains_how_to_enable_the_analysis(caplog):
    with caplog.at_level("INFO"):
        openrouter.log_analysis_unavailable()

    assert "OPENROUTER_API_KEY" in caplog.text


class TestPromptFormat:
    """The prompt describes the game the deck is actually played in."""

    def _prompt(self, posted, fmt=None):
        kwargs = {"api_key": "key-123"}
        if fmt is not None:
            kwargs["fmt"] = fmt
        openrouter.analyze_deck_list(DECKLIST, **kwargs)
        return posted.call["json"]["messages"][0]["content"]

    def test_commander_prompt_describes_a_multiplayer_pod(self, posted):
        prompt = self._prompt(posted, "commander")
        assert "40 starting life" in prompt
        assert "four-player pod" in prompt

    def test_duel_prompt_describes_a_1v1_duel(self, posted):
        prompt = self._prompt(posted, "duel")
        assert "20 starting life" in prompt
        assert "1v1 duel" in prompt
        assert "four-player pod" not in prompt

    def test_the_prompt_names_the_format(self, posted):
        assert "Duel Commander" in self._prompt(posted, "duel")

    def test_the_default_is_still_commander(self, posted):
        prompt = self._prompt(posted)
        assert "40 starting life" in prompt
        assert "four-player pod" in prompt


def test_prompt_states_the_bracket_and_its_signals(posted):
    openrouter.analyze_deck_list(
        "1 Rhystic Study",
        api_key="k",
        bracket={
            "bracket": 3,
            "label": "Upgraded",
            "signals": {
                "game_changers": ["Rhystic Study"],
                "mass_land_denial": [],
                "extra_turns": [],
            },
        },
    )
    prompt = posted.call["json"]["messages"][0]["content"]
    assert "Bracket: 3 (Upgraded)" in prompt
    assert "Rhystic Study" in prompt
    assert "no mass land denial" in prompt
    assert "Do not re-estimate" in prompt


def test_prompt_is_unchanged_when_no_bracket_is_given(posted):
    openrouter.analyze_deck_list("1 Forest", api_key="k")
    prompt = posted.call["json"]["messages"][0]["content"]
    assert "Bracket" not in prompt


def test_prompt_uses_singular_wording_for_a_single_signal_card(posted):
    openrouter.analyze_deck_list(
        "1 Rhystic Study",
        api_key="k",
        bracket={
            "bracket": 3,
            "label": "Upgraded",
            "signals": {
                "game_changers": ["Rhystic Study"],
                "mass_land_denial": ["Armageddon"],
                "extra_turns": ["Time Warp"],
            },
        },
    )
    prompt = posted.call["json"]["messages"][0]["content"]
    assert "1 Game Changer (Rhystic Study)" in prompt
    assert "1 mass land denial card (Armageddon)" in prompt
    assert "1 extra-turn card (Time Warp)" in prompt


def test_prompt_uses_plural_wording_for_multiple_signal_cards(posted):
    openrouter.analyze_deck_list(
        "2 Rhystic Study\n1 Smothering Tithe",
        api_key="k",
        bracket={
            "bracket": 3,
            "label": "Upgraded",
            "signals": {
                "game_changers": ["Rhystic Study", "Smothering Tithe"],
                "mass_land_denial": ["Armageddon", "Iona"],
                "extra_turns": ["Time Warp", "Extra Turn"],
            },
        },
    )
    prompt = posted.call["json"]["messages"][0]["content"]
    assert "2 Game Changers (Rhystic Study, Smothering Tithe)" in prompt
    assert "2 mass land denial cards (Armageddon, Iona)" in prompt
    assert "2 extra-turn cards (Time Warp, Extra Turn)" in prompt
