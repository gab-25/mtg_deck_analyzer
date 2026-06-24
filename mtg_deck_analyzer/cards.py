"""Card classification by type and deck-type inference."""


def classify_card(card_data: dict) -> str:
    """Classifies a card based on its type line.

    Always uses the English `type_line` (the Scryfall oracle type), never the
    localized `printed_type_line` stored in `faces`, so classification keeps
    working regardless of the requested language.
    """
    type_line = card_data.get("type_line", "")
    if not type_line:
        # Fallback for data shapes that only carry per-face details.
        faces = card_data.get("faces", [])
        if faces:
            type_line = faces[0].get("type_line", "")

    tl = type_line.lower()

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


def infer_deck_type(processed_cards: list) -> str:
    """Infers the deck format from its size and singleton composition.

    Returns one of: "Commander / EDH", "Constructed", "Limited", "Custom".
    """
    total = sum(item["quantity"] for item in processed_cards)

    # Singleton check: every non-land card appears exactly once
    # (lands, especially basics, may legitimately repeat).
    singleton = all(
        item["quantity"] == 1
        for item in processed_cards
        if classify_card(item["data"]) != "Land"
    )

    if singleton and 95 <= total <= 105:
        return "Commander / EDH"
    if total >= 60:
        return "Constructed"
    if 40 <= total < 60:
        return "Limited"
    return "Custom"
