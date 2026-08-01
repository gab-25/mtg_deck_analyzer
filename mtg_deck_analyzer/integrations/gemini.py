"""Google Gemini integration: Commander deck analysis."""

import logging

from google import genai

from ..domain.constants import GEMINI_MODEL

logger = logging.getLogger(__name__)


def log_analysis_unavailable() -> None:
    """Logs to the console how to enable the Gemini analysis (nothing goes into the PDF)."""
    logger.info(
        "No Gemini API key configured: skipping deck analysis. The PDF will be "
        "generated without the strategy section. To enable it, obtain a Google "
        'Gemini API key and set the environment variable: export GEMINI_API_KEY="your_api_key"'
    )


def analyze_deck_list(
    deck_list_text: str, api_key: str = None, commanders: list = None
) -> str:
    """Queries Gemini to write a tactical strategy guide for the Commander deck.

    ``commanders`` are the deck's commander name(s); they anchor the analysis
    when known. Returns the analysis text, or None if it could not be produced
    (in which case nothing should be added to the PDF; the reason is logged to
    the console).
    """
    try:
        if api_key:
            client = genai.Client(api_key=api_key)
        else:
            client = genai.Client()
    except Exception as e:
        logger.warning(
            "Failed to initialize Google GenAI Client: %s. "
            "Skipping deck analysis (nothing will be added to the PDF).",
            e,
        )
        return None

    commander_line = (
        f"The deck's commander is: {', '.join(commanders)}.\n"
        if commanders
        else "The deck's commander is not declared: infer the most likely one "
        "from the list and say which you assumed.\n"
    )

    prompt = f"""You are an expert Magic: The Gathering Commander (EDH) strategist.
Write a strategy guide for the Commander deck below, entirely in English, using
clean GitHub-flavored Markdown.

CONTEXT — this is always a Commander deck:
- 100-card singleton, multiplayer (typically a four-player pod), 40 starting life.
- {commander_line.strip()}
- Judge the deck as a Commander deck: commander-centric game plan, color identity,
  ramp and mana base, card advantage engines, interaction, and multiplayer politics
  and threat assessment. Never discuss it as a 60-card constructed or limited deck.

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

    logger.info("Connecting to Gemini for strategic analysis...")
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        return response.text
    except Exception as e:
        logger.warning(
            "Gemini API generation failed: %s. "
            "Skipping deck analysis (nothing will be added to the PDF).",
            e,
        )
        return None
