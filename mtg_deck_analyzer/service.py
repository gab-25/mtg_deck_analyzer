"""Shared deck-analysis orchestration used by both the CLI and the web service.

This module wraps the parse -> Scryfall fetch -> Gemini analysis -> statistics
pipeline behind a single function so the workflow lives in exactly one place.
"""

import os
from typing import Any

from .cards import compute_statistics, infer_deck_type
from .constants import normalize_lang
from .decklist import parse_decklist_text
from .gemini import analyze_deck_list, log_analysis_unavailable
from .scryfall import FileCardCache, fetch_card_data
from .text_utils import localize_card_names


def default_cache_dir() -> str:
    """Returns (and creates) the default local cache directory for the package."""
    package_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(package_dir)
    cache_dir = os.path.join(project_dir, ".cache", "mtg_deck_analyzer")
    os.makedirs(os.path.join(cache_dir, "cards"), exist_ok=True)
    os.makedirs(os.path.join(cache_dir, "images"), exist_ok=True)
    return cache_dir


def analyze_decklist(
    decklist_text: str,
    lang: str = "en",
    api_key: str | None = None,
    *,
    cache=None,
    skip_analysis: bool = False,
    progress=None,
) -> dict[str, Any]:
    """Runs the full analysis pipeline on raw decklist text.

    ``cache`` is a Scryfall cache backend (see ``scryfall.FileCardCache`` or the
    web app's ``DbCardCache``); it defaults to a filesystem cache under the
    package's ``.cache`` directory. ``progress`` is an optional
    ``callable(message: str)`` used to report status (defaults to no-op).

    Returns a dict with the processed cards, the (optional) Gemini analysis text
    and the aggregate statistics. Raises ``ValueError`` if no cards could be
    parsed or fetched.
    """
    lang = normalize_lang(lang)
    api_key = api_key or os.environ.get("GEMINI_API_KEY")
    if cache is None:
        cache = FileCardCache(default_cache_dir())
    notify = progress or (lambda _msg: None)

    deck_cards = parse_decklist_text(decklist_text)
    if not deck_cards:
        raise ValueError("No cards could be parsed from the decklist.")

    notify(f"Parsed {len(deck_cards)} unique entries.")

    processed_cards = []
    # Maps the English name (as used in the analysis prompt) to the localized
    # name, so card mentions in the analysis can be translated afterwards.
    name_map = {}

    for idx, item in enumerate(deck_cards):
        name = item["name"]
        qty = item["quantity"]
        notify(f"[{idx + 1}/{len(deck_cards)}] Fetching '{name}' (x{qty})...")

        card_info = fetch_card_data(name, lang, cache, api_key)
        if card_info:
            processed_cards.append({"quantity": qty, "data": card_info})
            localized_name = card_info.get("name")
            if localized_name:
                name_map[name] = localized_name

    if not processed_cards:
        raise ValueError("Could not retrieve card details for any card.")

    deck_analysis = None
    if not skip_analysis:
        if api_key:
            deck_text_repr = "\n".join(
                f"{item['quantity']} {item['name']}" for item in deck_cards
            )
            deck_analysis = analyze_deck_list(
                deck_text_repr, api_key=api_key, lang_code=lang
            )
            if deck_analysis and lang != "en":
                deck_analysis = localize_card_names(deck_analysis, name_map)
        else:
            log_analysis_unavailable()

    total_cards, total_price, avg_cmc, category_counts = compute_statistics(
        processed_cards
    )

    return {
        "processed_cards": processed_cards,
        "deck_analysis": deck_analysis,
        "name_map": name_map,
        "stats": {
            "deck_type": infer_deck_type(processed_cards),
            "total_cards": total_cards,
            "total_value_eur": total_price,
            "avg_cmc": avg_cmc,
            "category_counts": category_counts,
        },
    }
