"""Command-line interface and workflow orchestration."""

import argparse
import os
import shutil
import sys

from .config import load_config
from .pdf import generate_pdf
from .service import analyze_decklist


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

    # 3-5. Parse, fetch and analyze through the shared service.
    print(f"Parsing decklist from '{filename}'...")
    print(f"Fetching card metadata and artwork (language: {lang})...")
    with open(deck_path, "r", encoding="utf-8") as f:
        decklist_text = f.read()

    try:
        result = analyze_decklist(
            decklist_text,
            lang=lang,
            api_key=api_key,
            cache_dir=cache_dir,
            skip_analysis=args.skip_analysis,
            progress=print,
        )
    except ValueError as e:
        print(f"Error: {e} Generation aborted.", file=sys.stderr)
        sys.exit(1)

    processed_cards = result["processed_cards"]
    deck_analysis = result["deck_analysis"]

    # 6. Generate the final PDF.
    print(f"Compiling deck analysis PDF to '{os.path.basename(output_pdf)}'...")
    try:
        generate_pdf(deck_name, deck_analysis, processed_cards, output_pdf)
        print(f"\nSuccess! PDF successfully generated at: {output_pdf}")
    except Exception as e:
        print(f"\nError compiling PDF: {e}", file=sys.stderr)
        sys.exit(1)
