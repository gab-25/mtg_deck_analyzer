"""Filesystem-backed Scryfall cache (card JSON + image bytes)."""

import json
import os


class FileCardCache:
    """Filesystem-backed Scryfall cache (card JSON + image bytes).

    This is the default backend, kept so the analysis engine works standalone
    (and in tests) without a database. Cards are keyed by a string like
    ``card_en_lightning_bolt`` and images by their basename (``img_<id>_<lang>.jpg``).
    """

    def __init__(self, cache_dir: str):
        self.cards_dir = os.path.join(cache_dir, "cards")
        self.images_dir = os.path.join(cache_dir, "images")
        os.makedirs(self.cards_dir, exist_ok=True)
        os.makedirs(self.images_dir, exist_ok=True)

    def get_card(self, key: str) -> dict | None:
        path = os.path.join(self.cards_dir, f"{key}.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None  # Treat a corrupt entry as a miss.

    def set_card(self, key: str, data: dict) -> None:
        path = os.path.join(self.cards_dir, f"{key}.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def has_image(self, name: str) -> bool:
        return os.path.exists(os.path.join(self.images_dir, name))

    def get_image(self, name: str) -> bytes | None:
        path = os.path.join(self.images_dir, name)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "rb") as f:
                return f.read()
        except Exception:
            return None

    def set_image(self, name: str, data: bytes) -> None:
        try:
            with open(os.path.join(self.images_dir, name), "wb") as f:
                f.write(data)
        except Exception:
            pass
