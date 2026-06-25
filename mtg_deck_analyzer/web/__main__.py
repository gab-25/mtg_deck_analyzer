"""Run the web service: ``python -m mtg_deck_analyzer.web`` or ``mtg-deck-web``."""

import os

import uvicorn


def main() -> None:
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    reload = os.environ.get("RELOAD", "").lower() in {"1", "true", "yes"}
    uvicorn.run("mtg_deck_analyzer.web.app:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    main()
