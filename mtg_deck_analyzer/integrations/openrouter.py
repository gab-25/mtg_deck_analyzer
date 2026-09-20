"""OpenRouter integration: Commander deck analysis.

OpenRouter proxies every provider it supports (Gemini, Claude, GPT, Llama, ...)
behind one OpenAI-compatible ``/chat/completions`` endpoint, so the model is a
setting rather than a dependency: see ``OPENROUTER_MODEL``.
"""

import logging
import os

import requests

from ..domain.constants import DEFAULT_FORMAT, FORMATS, OPENROUTER_MODEL

logger = logging.getLogger(__name__)

API_URL = "https://openrouter.ai/api/v1/chat/completions"

# The analysis runs in a background thread: a provider that never answers must
# not keep that thread (and the deck's "processing" status) hanging forever.
REQUEST_TIMEOUT = 180

# Optional attribution headers, used by OpenRouter to credit the calling app.
APP_URL = "https://github.com/gab-25/mtg_deck_analyzer"
APP_TITLE = "mtg_deck_analyzer"


def log_analysis_unavailable() -> None:
    """Logs to the console how to enable the analysis (nothing goes into the PDF)."""
    logger.info(
        "No OpenRouter API key configured: skipping deck analysis. The PDF will "
        "be generated without the strategy section. To enable it, obtain an "
        "OpenRouter API key and set the environment variable: export "
        'OPENROUTER_API_KEY="your_api_key"'
    )


def analyze_deck_list(
    deck_list_text: str,
    api_key: str = None,
    commanders: list = None,
    fmt: str = DEFAULT_FORMAT,
    bracket: dict = None,
) -> str | None:
    """Asks the configured model to write a tactical strategy guide for the deck.

    ``commanders`` are the deck's commander name(s); they anchor the analysis
    when known. ``fmt`` is the Commander format the deck is built for: it
    decides the game the model is asked to judge the deck in, which differs
    sharply between a four-player pod and a 1v1 duel. ``bracket`` is the
    computed Commander Bracket verdict; when given, the model is told the level
    instead of being asked to guess it. Returns the analysis text, or None if
    it could not be produced (in which case nothing should be added to the PDF;
    the reason is logged to the console).
    """
    api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        log_analysis_unavailable()
        return None

    commander_line = (
        f"The deck's commander is: {', '.join(commanders)}.\n"
        if commanders
        else "The deck's commander is not declared: infer the most likely one "
        "from the list and say which you assumed.\n"
    )

    rules = FORMATS[fmt]

    # The bracket is an input, not a question: the model is good at judgement
    # and prose, and bad at recalling which cards are Game Changers.
    bracket_lines = ""
    if bracket:
        signals = bracket.get("signals", {})

        def _signal(names: list, singular: str, plural: str, none_text: str) -> str:
            if not names:
                return none_text
            noun = singular if len(names) == 1 else plural
            return f"{len(names)} {noun} ({', '.join(names)})"

        detail = "; ".join(
            (
                _signal(signals.get("game_changers") or [],
                        "Game Changer", "Game Changers", "no Game Changers"),
                _signal(signals.get("mass_land_denial") or [],
                        "mass land denial card", "mass land denial cards",
                        "no mass land denial"),
                _signal(signals.get("extra_turns") or [],
                        "extra-turn card", "extra-turn cards",
                        "no extra-turn cards"),
            )
        )
        bracket_lines = (
            f"- Estimated Commander Bracket: {bracket['bracket']} "
            f"({bracket['label']}), a minimum estimate computed from the list: "
            f"{detail}.\n"
            "- Judge the deck at that bracket. Do not re-estimate it, dispute it, "
            "or name a different bracket number.\n"
        )

    prompt = f"""You are an expert Magic: The Gathering Commander (EDH) strategist.
Write a strategy guide for the {rules.label} deck below, entirely in English, using
clean GitHub-flavored Markdown.

CONTEXT — this is a {rules.label} deck:
- 100-card singleton, {rules.context}, {rules.life} starting life.
- {commander_line.strip()}
{bracket_lines}- Judge the deck as a {rules.label} deck: commander-centric game plan, color identity,
  ramp and mana base, card advantage engines, interaction, and the threat assessment
  this format calls for. Never discuss it as a 60-card constructed or limited deck.

STRICT FORMATTING RULES — follow exactly:
- Do NOT write any introduction, preamble, greeting, or closing remarks.
- Do NOT output a top-level document title or the deck's name as a heading; a section title is already placed above your text.
- Do NOT use horizontal rules (---, ***).
- Start directly with the first "## " section heading.
- Use exactly these four sections, in this order, prefixed with "## ":
  1. Commander & Archetype
  2. Game Plan (Early / Mid / Late game)
  3. Key Synergies & Combos
  4. Strengths & Weaknesses
- Under each section, write at most one short intro sentence, then use "- " bullet points.
- For the Game Plan, use "### " subheadings for Early / Mid / Late game.
- Bold actual card names and key terms with **double asterisks**.
- Be concise and concrete; reference real cards from the list below. No filler.

Deck list:
{deck_list_text}
"""

    model = os.environ.get("OPENROUTER_MODEL") or OPENROUTER_MODEL

    logger.info("Connecting to OpenRouter (%s) for strategic analysis...", model)
    try:
        response = requests.post(
            API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": APP_URL,
                "X-Title": APP_TITLE,
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as e:
        return _skipped("OpenRouter request failed: %s" % e)

    if response.status_code != 200:
        return _skipped(
            "OpenRouter returned HTTP %s: %s" % (response.status_code, response.text)
        )

    try:
        content = response.json()["choices"][0]["message"]["content"]
    except (ValueError, LookupError, TypeError) as e:
        return _skipped("Unexpected OpenRouter response (%s): %s" % (e, response.text))

    if not content or not content.strip():
        return _skipped("OpenRouter returned an empty completion.")

    return content


def _skipped(reason: str) -> None:
    """Logs why the analysis was skipped and returns None (nothing to render)."""
    logger.warning(
        "%s Skipping deck analysis (nothing will be added to the PDF).", reason
    )
    return None
