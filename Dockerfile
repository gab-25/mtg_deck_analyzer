# Web service image for the MTG Deck Analyzer (Django).
FROM python:3.14-slim

# Install uv (fast Python package manager).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install dependencies first for better layer caching.
COPY pyproject.toml uv.lock README.md ./
COPY mtg_deck_analyzer ./mtg_deck_analyzer
RUN uv sync --frozen --no-dev

ENV HOST=0.0.0.0 \
    PORT=8000

EXPOSE 8000

CMD ["uv", "run", "--no-dev", "mtg-deck-analyzer"]
