# MTG Deck Analyzer

A **Django** web app for Magic: The Gathering. Paste a decklist in the browser and it fetches card images and descriptions in real time through the **Scryfall** API, produces a strategic deck analysis with **Google Gemini** (via the official `google-genai` SDK), and renders an interactive report (**HTMX + DaisyUI**) backed by a **Postgres** database — with a one-click download of the same report as a professional **PDF**.

See [Web Service](#web-service) to get it running.

## Features

- **Fact Sheet & Statistics**: Adds a summary info box at the top of the PDF containing:
  - Total number of cards in the deck.
  - Estimated total monetary value based on **Cardmarket** prices (in Euros).
  - Average Mana Value (CMC) computed excluding lands.
  - Detailed breakdown of the card types present (e.g. Creatures, Lands, Enchantments, Instants, etc.).
- **Category-Grouped List**: Organizes the deck by grouping cards by type (Creatures, Lands, Enchantments, Sorceries, Instants, Artifacts, Planeswalkers, etc.), showing the total count per category.
- **Individual & Cumulative Prices**: Shows the estimated Cardmarket price of each card next to its title. For quantities greater than 1x, it shows both the unit price and the accumulated total for that stack (e.g. `15x Forest €0.05 (€0.75 tot)`).
- **Multi-language card content**: Fetches card names and descriptions in the chosen language (English, Italian, Spanish, French, German — defined in a single registry in `constants.py`). If a card is not available in the chosen language it falls back intelligently: first to an alternative set that has it localized, then to a Gemini machine translation, and finally to the English text. Each card records its text **provenance** (`official` / `machine` / `english`), surfaced as an "Auto-translated" or "English text" badge in the web page and a note in the PDF, so machine-translated rules text is never passed off as official. The interface itself stays in English.
- **Gemini Analysis**: Analyzes the deck's archetype and gameplay strategy (early, mid, and late game, synergies, and combos) using the `gemini-2.5-flash` model. If no API key is configured, the analysis is simply skipped and logged to the console — the PDF is generated without the strategy section (no placeholder block is inserted).
- **Complex Card Support**: Correctly handles double-faced cards (showing both faces side by side in the PDF), split cards, adventures, and rooms.
- **Scryfall Cache in the Database**: Card JSON and images are cached in Postgres (tables `scryfall_cards` and `scryfall_images`), shared across all decks, to avoid overloading the Scryfall API and make subsequent analyses fast. The cache backend is pluggable — a filesystem cache is also available when the engine is used standalone.
- **Aesthetic PDF Layout**: Generates a clean, modern, and elegant A4 PDF with dynamic headers and footers including page numbers, and aligned tables.
- **Interactive Web UI**: Submit decklists from the browser, browse previously analyzed decks stored in Postgres, and view each report as a page (fact sheet, Gemini analysis, grouped card list) with a PDF download — built with HTMX and DaisyUI (see [Web Service](#web-service)).

---

## Project Structure

The code is organized as a flat, direct Python package:

```
manage.py              # Django management entrypoint
mtg_deck_analyzer/
├── __init__.py        # Package metadata and dotenv loading
├── __main__.py        # Server entrypoint (mtg-deck-analyzer): migrate + runserver
├── settings.py        # Django settings (DATABASE_URL parsing, apps, middleware)
├── settings_test.py   # Test settings (in-memory SQLite)
├── urls.py            # URL routing
├── wsgi.py / asgi.py  # WSGI/ASGI application entry points
├── views.py           # Django views (HTMX + DaisyUI)
├── apps.py            # Django app configuration
├── models.py          # ORM models (Deck, ScryfallCard, ScryfallImage)
├── migrations/        # Database migrations
├── templates/         # Django templates
├── pipeline.py        # Analysis pipeline (parse → fetch → analyze → stats)
├── domain/            # Pure domain logic (no I/O, no Django)
│   ├── constants.py   #   Shared constants (Scryfall headers, language maps, categories)
│   ├── decklist.py    #   Decklist text parsing
│   ├── cards.py       #   Card classification and aggregate statistics
│   ├── text_utils.py  #   Slugs and Markdown -> ReportLab Flowables conversion
│   └── storage.py     #   Card image (de)serialization for storage/PDF
├── integrations/      # External service clients
│   ├── scryfall.py    #   Card data/image fetching from Scryfall
│   └── gemini.py      #   Card translation and strategic analysis (Google Gemini)
├── caching/           # Scryfall cache backends
│   ├── file_cache.py  #   Filesystem-backed cache (default, standalone/tests)
│   └── db_cache.py    #   Database-backed cache backend
└── rendering/
    └── pdf.py         # PDF generation
```

---

## Installation

The tool uses `uv` as a fast and efficient Python package manager.

1. **Clone the repository** and enter the project folder.
2. Make sure `uv` is installed on your system. Otherwise, install it:
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
3. Sync the virtual environment:
   ```bash
   uv sync
   ```

---

## Configuration

The app is configured entirely through environment variables (loaded from a
`.env` file during local development — see [Run locally](#run-locally-without-docker)):

- `GEMINI_API_KEY` — enables the strategic analysis and card translation. Without a key the app still works, simply skipping the strategy section.
- `DEFAULT_LANG` — default target language code for card names and analysis (defaults to `en`). The language can also be chosen per-deck in the web form.

---

## Web Service

The app is a **Django** web service with a **Postgres** database and
**HTMX + DaisyUI** pages. You paste a decklist, pick a language, and get a web
page with the deck fact sheet, the Gemini strategy analysis, and the full card
list — plus a one-click **PDF download** of the report.

### Run with Docker Compose (recommended)

This starts Postgres and the web app together:

```bash
# Optional: enable the Gemini strategic analysis.
export GEMINI_API_KEY="your_api_key_here"

docker compose up --build
```

Then open <http://localhost:8000>. Everything — decks and the Scryfall cache
(card JSON + images) — lives in Postgres, persisted to a named Docker volume.

### Run locally (without Docker)

Copy the example environment file and adjust it — it is loaded automatically on
startup (real environment variables still take precedence):

```bash
cp .env.example .env
# edit .env: DATABASE_URL, GEMINI_API_KEY, HOST/PORT/RELOAD
uv run mtg-deck-analyzer
```

The relevant variables are:

- `DATABASE_URL` — a Postgres or SQLite URL (default `postgresql://mtg:mtg@localhost:5432/mtg`). Point it at any Postgres instance, or use `sqlite:///./mtg.db` for a quick, dependency-free run. A `+driver` suffix on the scheme (e.g. `postgresql+psycopg://…`) is accepted and ignored.
- `GEMINI_API_KEY` — optional; enables the strategic analysis.
- `DEFAULT_LANG` — optional; default target language code (defaults to `en`).
- `HOST` / `PORT` — server bind address (defaults `0.0.0.0:8000`).
- `RELOAD` — set to `1` for auto-reload during development.
- `SECRET_KEY` / `DEBUG` — Django secret key and debug flag (sensible defaults for local development).

Database migrations are applied automatically on startup.

The Gemini API key and the default language are resolved from the
environment variables described in [Configuration](#configuration) above.
Without a key the app still works, simply skipping the strategy section.

---

## Decklist Format

Paste one line per card into the form, formatted with the quantity followed by the card name (exactly as exported from Arena or MTGO). For example:

```text
1 Aid from the Cowl
1 Apex Devastator
15 Forest
1 Meat Locker/Drowned Diner
1 Repudiate/Replicate
1 Tatyova, Benthic Druid
```

Empty lines and comments starting with `//` or `#` are automatically ignored by the parser.

---

## Technical Details

- **ReportLab Platypus**: Used to manage the content flow and ensure smooth pagination.
- **Scryfall API Guidelines**: The tool respects the rate limit imposed by Scryfall by introducing a controlled `100ms` delay between requests when data is not cached.
- **Pillow**: Used to decode and scale the card images before placing them in the PDF layout.
