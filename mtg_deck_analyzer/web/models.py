"""SQLAlchemy ORM models."""

import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy import JSON as SA_JSON
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class Deck(Base):
    """A submitted deck together with its fetched cards and analysis."""

    __tablename__ = "decks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    lang: Mapped[str] = mapped_column(String(8), nullable=False, default="en")
    raw_decklist: Mapped[str] = mapped_column(Text, nullable=False)

    # Strategic analysis (GitHub-flavored Markdown), or NULL when unavailable.
    analysis_md: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Aggregate statistics.
    deck_type: Mapped[str] = mapped_column(String(64), default="Custom")
    total_cards: Mapped[int] = mapped_column(Integer, default=0)
    total_value_eur: Mapped[float] = mapped_column(Float, default=0.0)
    avg_cmc: Mapped[float] = mapped_column(Float, default=0.0)
    category_counts: Mapped[dict] = mapped_column(SA_JSON, default=dict)

    # Processed card list: ``[{"quantity": int, "data": {...}}]`` where each
    # card's ``image_paths`` are stored as cache-relative basenames.
    cards: Mapped[list] = mapped_column(SA_JSON, default=list)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
