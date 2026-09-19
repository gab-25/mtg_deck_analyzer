# MTG Deck Analyzer

A **Django** web app for Magic: The Gathering **Commander (EDH)** decks. Paste a Commander decklist in the browser and it fetches card images and descriptions in real time through the **Scryfall** API, produces a strategic deck analysis with an LLM of your choice through **OpenRouter**, and renders an interactive report (**HTMX + Tailwind CSS**) backed by a **Postgres** database — with a one-click download of the same report as a professional **PDF**.

Commander is the only format the app handles: there is no format selection and no
format detection. Every deck is parsed, validated, analyzed and rendered as a
100-card singleton Commander deck.

See [Web Service](#web-service) to get it running.

## Features

- **Commander-aware**: The commander is a first-class citizen — declared in the decklist, highlighted on the deck page (art, type line, badge on its card row), printed on the PDF fact sheet, and used to anchor the AI analysis. The deck's color pips come from the commander's **color identity**, not from the mana costs it happens to play.
- **Commander legality checks**: A decklist that is not a legal deck is never stored. Rules that plain text can settle — exactly 100 cards, exactly one commander, singleton except basic lands and "any number" cards — are checked instantly and reported *all at once* in the form. Rules that need the real cards — the commander is a legendary creature (or says it can be your commander), every card sits inside its color identity, and no card is on the ban list of the deck's format — are enforced during the analysis, which fails with the same kind of explanation.
- **Commander and Duel Commander**: A deck declares its format on creation. The two share their construction rules but not their ban lists — 186 cards legal in Commander are banned in Duel, Sol Ring included — so the deck is checked against the one it claims, and the AI analysis judges it as a pod deck or a 1v1 deck accordingly.
- **Fact Sheet & Statistics**: Adds a summary info box at the top of the PDF containing:
  - The format (always Commander) and the deck's commander.
  - Total number of cards in the deck.
  - Estimated total monetary value based on **Cardmarket** prices (in Euros).
  - Average Mana Value (CMC) computed excluding lands.
  - Detailed breakdown of the card types present (e.g. Creatures, Lands, Enchantments, Instants, etc.).
- **Category-Grouped List**: Organizes the deck by grouping cards by type (Creatures, Lands, Enchantments, Sorceries, Instants, Artifacts, Planeswalkers, etc.), showing the total count per category.
- **Individual & Cumulative Prices**: Shows the estimated Cardmarket price of each card next to its title. For quantities greater than 1x, it shows both the unit price and the accumulated total for that stack (e.g. `15x Forest €0.05 (€0.75 tot)`).
- **Multi-language card content**: Fetches card names and descriptions in the chosen language (English, Italian, Spanish, French, German — defined in a single registry in `constants.py`). If a card is not available in the chosen language it falls back intelligently: first to an alternative set that has it localized, then to a machine translation, and finally to the English text. Each card records its text **provenance** (`official` / `machine` / `english`), surfaced as an "Auto-translated" or "English text" badge in the web page and a note in the PDF, so machine-translated rules text is never passed off as official. The interface itself stays in English.
- **AI Analysis**: Analyzes the deck as a Commander deck — commander and archetype, multiplayer game plan (early, mid, and late game), synergies and combos, strengths and weaknesses. The request goes through [OpenRouter](https://openrouter.ai)'s OpenAI-compatible endpoint, so the app is not tied to a single provider: the default model is `google/gemini-2.5-flash`, and any other model id (Claude, GPT, Llama, ...) can be selected with the `OPENROUTER_MODEL` environment variable, without touching the code. The commander's name is passed into the prompt, and the model is told it is judging a 100-card singleton deck in a multiplayer pod. If no API key is configured, the analysis is simply skipped and logged to the console — the PDF is generated without the strategy section (no placeholder block is inserted).
- **Complex Card Support**: Correctly handles double-faced cards, split cards, adventures, and rooms. Both faces of a double-faced card are shown side by side in the PDF, flipped with a button in the card zoom on the web page, and printed as two adjacent cards on the proxy sheet.
- **Scryfall Cache in the Database**: Card JSON and images are cached in Postgres (tables `scryfall_cards` and `scryfall_images`), shared across all decks, to avoid overloading the Scryfall API and make subsequent analyses fast. The cache backend is pluggable — a filesystem cache is also available when the engine is used standalone.
- **Aesthetic PDF Layout**: Generates a clean, modern, and elegant A4 PDF with dynamic headers and footers including page numbers, and aligned tables.
- **Interactive Web UI**: Submit Commander decklists from the browser, browse previously analyzed decks stored in Postgres, and view each report as a page (commander panel, fact sheet, AI analysis, grouped card list) with a PDF download — built with HTMX and Tailwind CSS (see [Web Service](#web-service)).
- **Deck ownership and sharing**: A deck belongs to the user who submitted it. Your library shows your decks and nobody else's, and only you can edit, re-analyze or delete them. Each deck is **private** by default; switching it to **unlisted** makes it readable by anyone holding the link — no share token is needed, because a deck's id is a UUID and deck URLs are not enumerable. Unlisted grants reading only: it never opens the edit, delete or re-analyze actions. Decks created before ownership existed stay ownerless and keep behaving exactly as they did. Deleting an account deletes its decks and their version history along with it — this is irreversible, so it never leaves those decks ownerless and exposed instead.
- **Version history**: Every submitted card list is recorded as an append-only version, on creation and on each change to the list (a rename is not a version). The deck page shows the trail newest-first, each version with its changelog against the one before it — `+1 Rhystic Study` / `-1 Arcane Signet`, computed as plain set arithmetic over the parsed lists — plus an optional note explaining the revision, and any older list can be opened in full. Restoring an old version is deliberately not offered.

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
├── views.py           # Django views (HTMX + Tailwind CSS)
├── apps.py            # Django app configuration
├── access.py          # Deck ownership and visibility rules (one source of truth)
├── models.py          # ORM models (Deck, DeckVersion, ScryfallCard, ScryfallImage)
├── migrations/        # Database migrations
├── templates/         # Django templates
├── pipeline.py        # Analysis pipeline (parse → fetch → validate → analyze → stats)
├── domain/            # Pure domain logic (no I/O, no Django)
│   ├── constants.py   #   Shared constants (Scryfall headers, Commander rules, categories)
│   ├── decklist.py    #   Decklist text parsing (sections, commander detection)
│   ├── changelog.py   #   Differences between two decklists (+1 / -1 entries)
│   ├── commander.py   #   Commander format rules (color identity, legality, ban list)
│   ├── cards.py       #   Card classification and aggregate statistics
│   ├── text_utils.py  #   Slugs and Markdown -> ReportLab Flowables conversion
│   └── storage.py     #   Card image (de)serialization for storage/PDF
├── integrations/      # External service clients
│   ├── scryfall.py    #   Card data/image fetching from Scryfall
│   └── openrouter.py  #   Strategic deck analysis (LLM via OpenRouter)
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

- `OPENROUTER_API_KEY` — enables the strategic analysis. Without a key the app still works, simply skipping the strategy section.
- `OPENROUTER_MODEL` — the model the analysis runs on, as an [OpenRouter model id](https://openrouter.ai/models) (default `google/gemini-2.5-flash`).

---

## Web Service

The app is a **Django** web service with a **Postgres** database and
**HTMX + Tailwind CSS** pages. You paste a decklist and get a web page with the deck
fact sheet, the AI strategy analysis, and the full card list — plus a
one-click **PDF download** of the report.

### Run with Docker Compose (recommended)

This starts Postgres and the web app together:

```bash
# Optional: enable the strategic analysis.
export OPENROUTER_API_KEY="your_api_key_here"
# Optional: pick another model (default google/gemini-2.5-flash).
export OPENROUTER_MODEL="anthropic/claude-sonnet-4"

docker compose up --build
```

Then open <http://localhost:8000>. Everything — decks and the Scryfall cache
(card JSON + images) — lives in Postgres, persisted to a named Docker volume.

### Run locally (without Docker)

Copy the example environment file and adjust it — it is loaded automatically on
startup (real environment variables still take precedence):

```bash
cp .env.example .env
# edit .env: DATABASE_URL, OPENROUTER_API_KEY, HOST/PORT/RELOAD
uv run mtg-deck-analyzer
```

The relevant variables are:

- `DATABASE_URL` — a Postgres or SQLite URL (default `postgresql://mtg:mtg@localhost:5432/mtg`). Point it at any Postgres instance, or use `sqlite:///./mtg.db` for a quick, dependency-free run.
- `OPENROUTER_API_KEY` — optional; enables the strategic analysis.
- `OPENROUTER_MODEL` — optional; the OpenRouter model id used for the analysis (default `google/gemini-2.5-flash`).
- `HOST` / `PORT` — server bind address (defaults `0.0.0.0:8000`).
- `RELOAD` — set to `1` for auto-reload during development.
- `SECRET_KEY` / `DEBUG` — Django secret key and debug flag (sensible defaults for local development).

Database migrations are applied automatically on startup.

The OpenRouter API key is resolved from the environment variables described in
[Configuration](#configuration) above.
Without a key the app still works, simply skipping the strategy section.

---

## Decklist Format

Paste one line per card into the form, formatted with the quantity followed by the
card name (exactly as exported from Moxfield, Archidekt, Arena or MTGO). Declare the
commander under a `Commander` header, or tag its line with `*CMDR*`:

```text
Commander
1 Tatyova, Benthic Druid

Deck
1 Aid from the Cowl
1 Apex Devastator
1 Meat Locker/Drowned Diner
1 Repudiate/Replicate
39 Forest
```

The parser also accepts the `1x Sol Ring` quantity spelling, ignores empty lines and
comments starting with `//` or `#`, and skips section headers (`Deck`, `Mainboard`,
`Sideboard`, …). Commander has no sideboard, so cards under those headers are *not*
dropped: they count towards the deck and will show up as a size violation.

### Commander rules the app enforces

A deck is only stored once it satisfies all of these:

| Rule | When it's checked |
| --- | --- |
| Exactly 100 cards, commander included | on submit — the form rejects the deck |
| Exactly one commander is declared (partners and backgrounds are not accepted) | on submit |
| Singleton: one copy per card, except basic lands and "any number" cards such as Relentless Rats | on submit |
| The commander is a legendary creature, or says it can be your commander | during the analysis |
| Every card sits inside the commander's color identity | during the analysis |
| No card is banned in the deck's format, or was never legal in it | during the analysis |

The first three need nothing but the pasted text, so they are reported instantly and
all at once in the form. The last three need the real cards from Scryfall, so they run
in the background analysis: the deck is marked as failed with the same explanation
instead of being stored as ready.

### Formats

A deck declares which Commander format it is built for, and is validated against that
format's ban list only:

| Format | Ban list | Game |
| --- | --- | --- |
| **Commander** | the regular EDH list | multiplayer, four-player pod, 40 life |
| **Duel Commander** | the 1v1 list, far stricter | 1v1, 20 life |

Deck construction is identical in both — 100 cards, singleton, one commander — so only
the ban list and the strategic advice change. The difference is not cosmetic: **186
cards are legal in Commander and banned in Duel Commander**, Sol Ring, Dark Ritual and
Ancient Tomb among them. The format also reaches the AI analysis, which judges a Duel
deck as a 1v1 deck instead of a pod deck.

Changing a stored deck's format re-runs the analysis, since it has to be re-validated
against the other ban list.

---

## Technical Details

- **ReportLab Platypus**: Used to manage the content flow and ensure smooth pagination.
- **Scryfall API Guidelines**: The tool respects the rate limit imposed by Scryfall by introducing a controlled `100ms` delay between requests when data is not cached.
- **Pillow**: Used to decode and scale the card images before placing them in the PDF layout.
