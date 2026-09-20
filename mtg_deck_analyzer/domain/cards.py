"""Card classification by type and aggregate deck statistics."""

from .constants import CATEGORY_ORDER


def front_type_line(card_data: dict) -> str:
    """Returns the English type line of the card's front face, lowercased.

    A double-faced card carries a combined ``"Instant // Land"`` type line at
    the top level, which would file every spell with a land back under Lands.
    The front face is what the card is cast as, so it decides: the per-face
    details when they are there, the combined line split on ``//`` otherwise
    (decks stored before the faces carried their own type line).
    """
    faces = card_data.get("faces", [])
    type_line = faces[0].get("type_line", "") if faces else ""
    if not type_line:
        type_line = card_data.get("type_line", "")

    return type_line.split("//")[0].strip().lower()


def rules_text(card_data: dict) -> str:
    """All of a card's rules text, every face, lowercased.

    The single place card text is read from, so the rules checks and the
    functional tagging always see the same string.
    """
    faces = card_data.get("faces", [])
    return "\n".join(face.get("rules_text", "") or "" for face in faces).lower()


def classify_card(card_data: dict) -> str:
    """Classifies a card based on the type line of its front face."""
    tl = front_type_line(card_data)

    if "land" in tl:
        return "Land"
    elif "creature" in tl:
        return "Creature"
    elif "planeswalker" in tl:
        return "Planeswalker"
    elif "instant" in tl:
        return "Instant"
    elif "sorcery" in tl:
        return "Sorcery"
    elif "artifact" in tl:
        return "Artifact"
    elif "enchantment" in tl:
        return "Enchantment"
    elif "battle" in tl:
        return "Battle"
    else:
        return "Other"


def is_basic_land(card_data: dict) -> bool:
    """Reports whether a card is a basic land (``Basic Land — ...``).

    Reads the front face, matching :func:`classify_card`.
    """
    tl = front_type_line(card_data)
    return "basic" in tl and "land" in tl


def compute_statistics(processed_cards: list):
    """Computes aggregate deck statistics (totals, price, average CMC, counts).

    Returns a tuple ``(total_cards, total_price, avg_cmc, category_counts)``.
    """
    total_cards = 0
    total_price = 0.0
    total_non_land_cards = 0
    total_non_land_cmc = 0.0

    category_counts = {cat: 0 for cat in CATEGORY_ORDER}

    for item in processed_cards:
        qty = item["quantity"]
        card = item["data"]
        cat = classify_card(card)
        category_counts[cat] = category_counts.get(cat, 0) + qty

        total_cards += qty
        total_price += qty * card.get("price_eur", 0.0)

        if cat != "Land":
            total_non_land_cards += qty
            total_non_land_cmc += qty * card.get("cmc", 0.0)

    avg_cmc = (
        (total_non_land_cmc / total_non_land_cards) if total_non_land_cards > 0 else 0.0
    )

    return total_cards, total_price, avg_cmc, category_counts
