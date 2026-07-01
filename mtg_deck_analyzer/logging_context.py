"""Per-analysis logging context.

An analysis runs across several modules (pipeline, Scryfall, Gemini); rather than
threading the deck id through every call, we stash it in a :class:`ContextVar` for
the duration of the run and let :class:`DeckIdFilter` stamp it onto every log
record. ``contextvars`` are isolated per thread, so concurrent background analyses
don't leak ids into each other.
"""

import contextlib
import logging
from contextvars import ContextVar

_deck_id_var: ContextVar[str | None] = ContextVar("deck_id", default=None)


@contextlib.contextmanager
def deck_log_context(deck_id):
    """Binds ``deck_id`` to every log record emitted inside the ``with`` block."""
    token = _deck_id_var.set(str(deck_id))
    try:
        yield
    finally:
        _deck_id_var.reset(token)


class DeckIdFilter(logging.Filter):
    """Adds a ``deck_id`` field (``"[deck <id>] "`` or ``""``) to each record."""

    def filter(self, record: logging.LogRecord) -> bool:
        deck_id = _deck_id_var.get()
        record.deck_id = f"[deck {deck_id}] " if deck_id else ""
        return True
