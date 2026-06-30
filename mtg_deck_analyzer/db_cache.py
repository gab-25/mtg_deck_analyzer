"""Database-backed Scryfall cache.

Implements the cache-backend interface expected by ``scryfall.fetch_card_data``
(``get_card``/``set_card``/``has_image``/``get_image``/``set_image``), storing
card JSON and image bytes in the database (via the Django ORM) instead of on the
filesystem.
"""

from .models import ScryfallCard, ScryfallImage


class DbCardCache:
    """Scryfall cache backed by the ``scryfall_cards`` / ``scryfall_images`` tables."""

    def get_card(self, key: str) -> dict | None:
        row = ScryfallCard.objects.filter(pk=key).first()
        return row.data if row is not None else None

    def set_card(self, key: str, data: dict) -> None:
        ScryfallCard.objects.update_or_create(key=key, defaults={"data": data})

    def has_image(self, name: str) -> bool:
        return ScryfallImage.objects.filter(pk=name).exists()

    def get_image(self, name: str) -> bytes | None:
        row = ScryfallImage.objects.filter(pk=name).first()
        return bytes(row.data) if row is not None else None

    def set_image(self, name: str, data: bytes) -> None:
        if not self.has_image(name):
            ScryfallImage.objects.create(name=name, data=data)
