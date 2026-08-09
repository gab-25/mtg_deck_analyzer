"""Shared Commander deck-analysis orchestration used across the web service.

This module wraps the parse -> Scryfall fetch -> Gemini analysis -> statistics
pipeline behind a single function so the workflow lives in exactly one place.
"""

import os

from .caching.file_cache import FileCardCache
from .domain.cards import compute_statistics
from .domain.commander import check_deck, commander_names, deck_color_identity
from .domain.decklist import parse_decklist_text
from .integrations.gemini import analyze_deck_list, log_analysis_unavailable
from .integrations.scryfall import fetch_card_data


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
    api_key: str = None,
    *,
    cache=None,
    skip_analysis: bool = False,
    progress=None,
) -> dict:
    """Runs the full Commander analysis pipeline on raw decklist text.

    ``cache`` is a Scryfall cache backend (see ``caching.file_cache.FileCardCache``
    or ``caching.db_cache.DbCardCache``); it defaults to a filesystem cache under the
    package's ``.cache`` directory. ``progress`` is an optional
    ``callable(message: str)`` used to report status (defaults to no-op).

    Returns a dict with the processed cards, the (optional) Gemini analysis text
    and the aggregate statistics — including the deck's commander(s) and color
    identity. Raises ``ValueError`` if no cards could be parsed or fetched, or
    if the deck breaks the Commander deck-construction rules.
    """
    api_key = api_key or os.environ.get("GEMINI_API_KEY")
    if cache is None:
        cache = FileCardCache(default_cache_dir())
    notify = progress or (lambda _msg: None)

    deck_cards = parse_decklist_text(decklist_text)
    if not deck_cards:
        raise ValueError("No cards could be parsed from the decklist.")

    notify(f"Parsed {len(deck_cards)} unique entries.")

    processed_cards = []
    unresolved = []

    for idx, item in enumerate(deck_cards):
        name = item["name"]
        qty = item["quantity"]
        notify(f"[{idx + 1}/{len(deck_cards)}] Fetching '{name}' (x{qty})...")

        card_info = fetch_card_data(name, cache)
        if card_info:
            processed_cards.append(
                {
                    "quantity": qty,
                    "is_commander": item.get("is_commander", False),
                    "data": card_info,
                }
            )
        else:
            unresolved.append(name)

    if not processed_cards:
        raise ValueError("Could not retrieve card details for any card.")

    # A card that didn't resolve is missing from the deck, which would surface as
    # a puzzling "99 cards" further down: name the culprits instead.
    if unresolved:
        raise ValueError(
            "These cards could not be found on Scryfall (check their spelling):\n"
            + "\n".join(f"• {name}" for name in unresolved)
        )

    # Only a legal Commander deck is worth analyzing (and storing): report every
    # problem at once so the whole deck can be fixed in one pass.
    issues = check_deck(processed_cards)
    if issues:
        raise ValueError(
            "This is not a legal Commander deck:\n"
            + "\n".join(f"• {issue}" for issue in issues)
        )

    commanders = commander_names(processed_cards)
    deck_text_repr = _deck_text(deck_cards)

    deck_analysis = None
    if not skip_analysis:
        if api_key:
            deck_analysis = analyze_deck_list(
                deck_text_repr, api_key=api_key, commanders=commanders
            )
        else:
            log_analysis_unavailable()

    total_cards, total_price, avg_cmc, category_counts = compute_statistics(
        processed_cards
    )

    return {
        "processed_cards": processed_cards,
        "deck_analysis": deck_analysis,
        "stats": {
            "commanders": commanders,
            "color_identity": deck_color_identity(processed_cards),
            "total_cards": total_cards,
            "total_value_eur": total_price,
            "avg_cmc": avg_cmc,
            "category_counts": category_counts,
        },
    }


def _deck_text(deck_cards: list) -> str:
    """Renders the parsed decklist for the prompt, keeping the commander marked."""
    return "\n".join(
        f"{item['quantity']} {item['name']}"
        + (" *CMDR*" if item.get("is_commander") else "")
        for item in deck_cards
    )
