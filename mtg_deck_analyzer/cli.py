"""Command-line interface and workflow orchestration."""

import argparse
import os
import shutil
import sys

from .config import load_config
from .decklist import parse_decklist
from .gemini import analyze_deck_list, log_analysis_unavailable
from .pdf import generate_pdf
from .scryfall import fetch_card_data
from .text_utils import localize_card_names


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="MTG Deck List Analyzer. Generates beautiful PDF card reference sheets."
    )
    parser.add_argument(
        "deck_file",
        help="Path to the input text file containing the decklist.",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Path to save the output PDF file. Defaults to '[decklist_filename].pdf'.",
    )
    parser.add_argument(
        "-l",
        "--lang",
        default=None,
        help=(
            "Target language code for card names and details. "
            "Italian is 'it', Spanish 'es', French 'fr', German 'de'. "
            "Falls back to the config file, then to 'en'."
        ),
    )
    parser.add_argument(
        "--api-key",
        help=(
            "Google Gemini API Key. Falls back to the config file, "
            "then to the GEMINI_API_KEY environment variable."
        ),
    )
    parser.add_argument(
        "--config",
        help=(
            "Path to a TOML config file (keys: api_key, lang). "
            "Defaults to ./config.toml or config.toml in the project root."
        ),
    )
    parser.add_argument(
        "--skip-analysis",
        action="store_true",
        help="Skip requesting analysis from Gemini to save API usage.",
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Clears the local Scryfall cache before executing.",
    )
    return parser


def _setup_cache_dir(clear_cache: bool) -> str:
    """Prepares (and optionally clears) the local cache directory."""
    package_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(package_dir)
    cache_dir = os.path.join(project_dir, ".cache", "mtg_deck_analyzer")
    cards_cache_dir = os.path.join(cache_dir, "cards")
    images_cache_dir = os.path.join(cache_dir, "images")

    os.makedirs(cards_cache_dir, exist_ok=True)
    os.makedirs(images_cache_dir, exist_ok=True)

    if clear_cache:
        print("Clearing local Scryfall cache...")
        shutil.rmtree(cache_dir, ignore_errors=True)
        os.makedirs(cards_cache_dir, exist_ok=True)
        os.makedirs(images_cache_dir, exist_ok=True)

    return cache_dir


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)

    # 0. Resolve settings: CLI args > config file > environment > defaults.
    config = load_config(args.config)
    if config.get("path"):
        print(f"Using config file: {config['path']}")
    lang = (args.lang or config.get("lang") or "en").lower()
    api_key = args.api_key or config.get("api_key") or os.environ.get("GEMINI_API_KEY")

    # 1. Prepare paths.
    deck_path = os.path.abspath(args.deck_file)
    if not os.path.exists(deck_path):
        print(f"Error: Decklist file not found at '{args.deck_file}'", file=sys.stderr)
        sys.exit(1)

    filename = os.path.basename(deck_path)
    base_name, _ = os.path.splitext(filename)
    deck_name = base_name.replace("_", " ").replace("-", " ").title()

    output_pdf = args.output
    if not output_pdf:
        output_pdf = os.path.join(os.path.dirname(deck_path), f"{base_name}.pdf")

    # 2. Set up the local cache.
    cache_dir = _setup_cache_dir(args.clear_cache)

    # 3. Parse the decklist.
    print(f"Parsing decklist from '{filename}'...")
    deck_cards = parse_decklist(deck_path)
    if not deck_cards:
        print("No cards parsed. Please verify the input file contents.", file=sys.stderr)
        sys.exit(1)

    print(f"Parsed {len(deck_cards)} unique entries.")

    # 4. Fetch details and images from Scryfall.
    print(f"Fetching card metadata and artwork (language: {lang})...")
    processed_cards = []
    # Maps the English name (as used in the analysis prompt) to the localized
    # name, so card mentions in the analysis can be translated afterwards.
    name_map = {}

    for idx, item in enumerate(deck_cards):
        name = item["name"]
        qty = item["quantity"]

        print(f"[{idx+1}/{len(deck_cards)}] Fetching '{name}' (x{qty})... ", end="", flush=True)
        card_info = fetch_card_data(name, lang, cache_dir, api_key)

        if card_info:
            print("OK")
            processed_cards.append({"quantity": qty, "data": card_info})
            localized_name = card_info.get("name")
            if localized_name:
                name_map[name] = localized_name
        else:
            print("FAILED (Skipped)")

    if not processed_cards:
        print(
            "Error: Could not retrieve card details for any card. Generation aborted.",
            file=sys.stderr,
        )
        sys.exit(1)

    # 5. Strategic analysis with Gemini.
    deck_analysis = None
    if not args.skip_analysis:
        if api_key:
            deck_text_repr = "\n".join(
                [f"{item['quantity']} {item['name']}" for item in deck_cards]
            )
            deck_analysis = analyze_deck_list(
                deck_text_repr, api_key=api_key, lang_code=lang
            )
            # Translate the card names mentioned in the analysis into the target
            # language (the analysis is written from the English deck list).
            if deck_analysis and lang != "en":
                deck_analysis = localize_card_names(deck_analysis, name_map)
        else:
            # No API key: log to the console and leave the PDF without the analysis.
            log_analysis_unavailable()

    # 6. Generate the final PDF.
    print(f"Compiling deck analysis PDF to '{os.path.basename(output_pdf)}'...")
    try:
        generate_pdf(deck_name, deck_analysis, processed_cards, output_pdf)
        print(f"\nSuccess! PDF successfully generated at: {output_pdf}")
    except Exception as e:
        print(f"\nError compiling PDF: {e}", file=sys.stderr)
        sys.exit(1)
