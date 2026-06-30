"""Google Gemini integration: card translation and deck analysis."""

import json
import os

from google import genai
from google.genai import types

from ..domain.constants import DECK_TYPES, GEMINI_MODEL, LANG_MAP


def translate_card_via_gemini(
    card_name: str,
    oracle_text: str,
    type_line: str,
    lang_code: str,
    api_key: str = None,
) -> dict:
    """Translates card details into the target language using Gemini."""
    lang_name = LANG_MAP.get(lang_code.lower(), "Italian")

    prompt = f"""
    Translate the following Magic: The Gathering card details from English into {lang_name}.
    Use official MTG terminology rules for {lang_name} (e.g., in Italian, 'tap' is 'TAPpa', 'draw a card' is 'pesca una carta', 'flying' is 'volare').

    English Card:
    Name: {card_name}
    Type: {type_line}
    Text: {oracle_text}

    Return a JSON object with keys:
    "printed_name": (string, translated card name)
    "printed_type_line": (string, translated type line)
    "printed_text": (string, translated rules text)
    """

    try:
        if api_key:
            client = genai.Client(api_key=api_key)
        elif os.environ.get("GEMINI_API_KEY"):
            client = genai.Client()
        else:
            return {}  # Skip if no API key is available.

        config = types.GenerateContentConfig(response_mime_type="application/json")

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=config,
        )

        translated = json.loads(response.text.strip())
        return {
            "printed_name": translated.get("printed_name", "").strip(),
            "printed_type_line": translated.get("printed_type_line", "").strip(),
            "printed_text": translated.get("printed_text", "").strip(),
        }
    except Exception as e:
        print(f"\n[Warning] Gemini card translation failed: {e}")
        return {}


def recognize_deck_type(
    deck_list_text: str, api_key: str = None
) -> str | None:
    """Asks Gemini to classify the deck into one of :data:`DECK_TYPES`.

    Returns the matched type, or None if Gemini is unavailable or returns an
    unexpected value (callers should fall back to a heuristic in that case).
    """
    allowed = ", ".join(f'"{t}"' for t in DECK_TYPES)
    prompt = f"""You are an expert Magic: The Gathering deck classifier.
Classify the following deck into exactly one of these types: {allowed}.
Base your decision on the deck's size, format and composition.

Return a JSON object with a single key "deck_type" whose value is exactly one
of the allowed types (verbatim, including capitalization and spacing).

Deck list:
{deck_list_text}
"""

    try:
        if api_key:
            client = genai.Client(api_key=api_key)
        elif os.environ.get("GEMINI_API_KEY"):
            client = genai.Client()
        else:
            return None  # No API key: caller falls back to the heuristic.

        config = types.GenerateContentConfig(response_mime_type="application/json")
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=config,
        )

        deck_type = json.loads(response.text.strip()).get("deck_type", "").strip()
        return deck_type if deck_type in DECK_TYPES else None
    except Exception as e:
        print(f"\n[Warning] Gemini deck-type recognition failed: {e}")
        return None


def log_analysis_unavailable() -> None:
    """Logs to the console how to enable the Gemini analysis (nothing goes into the PDF)."""
    print("[Info] No Gemini API key configured: skipping deck analysis.")
    print("       The PDF will be generated without the strategy section.")
    print("       To enable it, obtain a Google Gemini API key and set the")
    print('       environment variable: export GEMINI_API_KEY="your_api_key"')


def analyze_deck_list(deck_list_text: str, api_key: str = None, lang_code: str = "en") -> str:
    """Queries Gemini to write a tactical strategy guide for the deck.

    Returns the analysis text, or None if it could not be produced (in which case
    nothing should be added to the PDF; the reason is logged to the console).
    """
    lang_name = LANG_MAP.get(lang_code.lower(), "English")

    try:
        if api_key:
            client = genai.Client(api_key=api_key)
        else:
            client = genai.Client()
    except Exception as e:
        print(f"\n[Warning] Failed to initialize Google GenAI Client: {e}")
        print("Skipping deck analysis (nothing will be added to the PDF).")
        return None

    prompt = f"""You are an expert Magic: The Gathering deck strategist.
Write a deck strategy guide entirely in {lang_name}, using clean GitHub-flavored Markdown.

STRICT FORMATTING RULES — follow exactly:
- Do NOT write any introduction, preamble, greeting, or closing remarks.
- Do NOT output a top-level document title or the deck's name as a heading; a section title is already placed above your text.
- Do NOT use horizontal rules (---, ***).
- Start directly with the first "## " section heading.
- Use exactly these four sections, in this order, with their titles translated into {lang_name} and prefixed with "## ":
  1. Overview & Archetype
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

    print("Connecting to Gemini for strategic analysis...")
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        return response.text
    except Exception as e:
        print(f"\n[Warning] Gemini API generation failed: {e}")
        print("Skipping deck analysis (nothing will be added to the PDF).")
        return None
