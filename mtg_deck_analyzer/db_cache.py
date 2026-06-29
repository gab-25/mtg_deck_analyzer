"""Database-backed Scryfall cache.

Implements the cache-backend interface expected by ``scryfall.fetch_card_data``
(``get_card``/``set_card``/``has_image``/``get_image``/``set_image``), storing
card JSON and image bytes in Postgres instead of on the filesystem.
"""

from sqlalchemy.orm import Session

from .models import ScryfallCard, ScryfallImage


class DbCardCache:
    """Scryfall cache backed by the ``scryfall_cards`` / ``scryfall_images`` tables."""

    def __init__(self, session: Session):
        self.session = session

    def get_card(self, key: str) -> dict | None:
        row = self.session.get(ScryfallCard, key)
        return row.data if row is not None else None

    def set_card(self, key: str, data: dict) -> None:
        row = self.session.get(ScryfallCard, key)
        if row is None:
            self.session.add(ScryfallCard(key=key, data=data))
        else:
            row.data = data
        self.session.commit()

    def has_image(self, name: str) -> bool:
        return self.session.get(ScryfallImage, name) is not None

    def get_image(self, name: str) -> bytes | None:
        row = self.session.get(ScryfallImage, name)
        return bytes(row.data) if row is not None else None

    def set_image(self, name: str, data: bytes) -> None:
        if self.session.get(ScryfallImage, name) is None:
            self.session.add(ScryfallImage(name=name, data=data))
            self.session.commit()
