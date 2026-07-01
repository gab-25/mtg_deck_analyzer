"""Fetching card data and images from Scryfall (with local cache)."""

import os
import time
import urllib.parse

import requests

from ..domain.constants import SCRYFALL_HEADERS
from ..domain.text_utils import get_card_slug
from .gemini import translate_card_via_gemini

# Polite delay between Scryfall requests (their guidelines ask for 50-100ms).
_REQUEST_DELAY = 0.1


def _scryfall_get(url: str, max_retries: int = 5):
    """GETs a Scryfall URL, retrying on rate limits (429) and transient errors.

    Returns the Response, or None if it could not be retrieved after retries.
    """
    for attempt in range(max_retries):
        time.sleep(_REQUEST_DELAY)
        try:
            resp = requests.get(url, headers=SCRYFALL_HEADERS, timeout=10)
        except requests.RequestException:
            # Network hiccup: back off and retry.
            time.sleep(0.5 * (attempt + 1))
            continue

        if resp.status_code == 429:
            # Rate limited: honor Retry-After if present, else exponential backoff.
            retry_after = resp.headers.get("Retry-After")
            try:
                wait = float(retry_after) if retry_after else 0.5 * (2**attempt)
            except ValueError:
                wait = 0.5 * (2**attempt)
            time.sleep(wait)
            continue

        return resp

    return None


def download_image(url: str) -> bytes | None:
    """Downloads an image from Scryfall and returns its bytes (or None)."""
    resp = _scryfall_get(url)
    if resp is not None and resp.status_code == 200:
        return resp.content
    return None


def get_face_details(face_or_card: dict) -> dict:
    """Extracts localized text details from a card or a face object."""
    name = face_or_card.get("printed_name") or face_or_card.get("name") or ""
    mana_cost = face_or_card.get("mana_cost") or ""
    type_line = face_or_card.get("printed_type_line") or face_or_card.get("type_line") or ""
    rules_text = face_or_card.get("printed_text") or face_or_card.get("oracle_text") or ""

    return {
        "name": name.strip(),
        "mana_cost": mana_cost.strip(),
        "type_line": type_line.strip(),
        "rules_text": rules_text.strip(),
    }


def _extract_price_eur(card: dict) -> float:
    """Extracts the EUR price, falling back to foil EUR and converted USD."""
    prices = card.get("prices", {}) or {}

    eur_str = prices.get("eur")
    if eur_str:
        try:
            return float(eur_str)
        except ValueError:
            pass

    eur_foil_str = prices.get("eur_foil")
    if eur_foil_str:
        try:
            return float(eur_foil_str)
        except ValueError:
            pass

    # Fallback to USD converted to EUR (~0.93 conversion rate).
    usd_str = prices.get("usd")
    if usd_str:
        try:
            return float(usd_str) * 0.93
        except ValueError:
            pass
    else:
        usd_foil_str = prices.get("usd_foil")
        if usd_foil_str:
            try:
                return float(usd_foil_str) * 0.93
            except ValueError:
                pass

    return 0.0


def process_cached_card(card: dict, cache) -> dict:
    """Processes Scryfall card JSON, caches missing images, and structures the data.

    The returned ``image_paths`` are cache *keys* (image basenames); the bytes
    themselves live in the cache backend.
    """
    card_id = card.get("id", "unknown")
    lang = card.get("lang", "en")
    image_names = []

    def _ensure_image(name: str, url: str) -> None:
        if not cache.has_image(name):
            data = download_image(url)
            if data:
                cache.set_image(name, data)
        if cache.has_image(name):
            image_names.append(name)

    # Check layout / image uris.
    if "image_uris" in card:
        # Single physical image.
        _ensure_image(f"img_{card_id}_{lang}.jpg", card["image_uris"]["normal"])

    elif (
        "card_faces" in card
        and len(card["card_faces"]) > 0
        and "image_uris" in card["card_faces"][0]
    ):
        # Double-sided card (distinct images per face).
        for idx, face in enumerate(card["card_faces"]):
            _ensure_image(
                f"img_{card_id}_{lang}_face{idx}.jpg", face["image_uris"]["normal"]
            )

    # Extract details.
    faces_details = []
    if "card_faces" in card and len(card["card_faces"]) > 0:
        # Multi-faced layout (split card, room, transform, adventure).
        # Note: for split/room cards the root has image_uris but card_faces holds the descriptions.
        for face in card["card_faces"]:
            faces_details.append(get_face_details(face))
    else:
        # Standard card.
        faces_details.append(get_face_details(card))

    return {
        "id": card_id,
        "name": card.get("printed_name") or card.get("name") or "Unknown Card",
        "image_paths": image_names,
        "faces": faces_details,
        "price_eur": _extract_price_eur(card),
        "type_line": card.get("type_line", ""),
        "cmc": card.get("cmc", 0.0),
        # Provenance of the localized text: "official" (Scryfall printed text),
        # "machine" (Gemini-translated) or "english" (no localization available).
        "text_source": card.get("_text_source"),
    }


def is_text_untranslated(card_data: dict) -> bool:
    """Checks whether the rules text is empty or identical to the English oracle text."""
    if "card_faces" in card_data and len(card_data["card_faces"]) > 0:
        for face in card_data["card_faces"]:
            printed = (face.get("printed_text") or "").strip()
            oracle = (face.get("oracle_text") or "").strip()
            if oracle and (not printed or printed == oracle):
                return True
        return False
    else:
        printed = (card_data.get("printed_text") or "").strip()
        oracle = (card_data.get("oracle_text") or "").strip()
        if oracle and (not printed or printed == oracle):
            return True
        return False


def find_best_translated_card(prints: list, lang: str) -> dict:
    """Finds the print with translated text, otherwise returns the first one."""
    if not prints:
        return None
    for card in prints:
        if not is_text_untranslated(card):
            return card
    return prints[0]


def _translate_card_data(card_data: dict, lang: str, api_key: str = None) -> None:
    """Translates card data in-place via Gemini when needed."""
    print(" (translating via Gemini)... ", end="", flush=True)
    if "card_faces" in card_data and len(card_data["card_faces"]) > 0:
        for face in card_data["card_faces"]:
            t_face = translate_card_via_gemini(
                face.get("name", ""),
                face.get("oracle_text", ""),
                face.get("type_line", ""),
                lang,
                api_key,
            )
            if t_face:
                face["printed_name"] = t_face.get("printed_name")
                face["printed_type_line"] = t_face.get("printed_type_line")
                face["printed_text"] = t_face.get("printed_text")
        card_data["printed_name"] = " // ".join(
            [f.get("printed_name") or f.get("name") for f in card_data["card_faces"]]
        )
    else:
        t_card = translate_card_via_gemini(
            card_data.get("name", ""),
            card_data.get("oracle_text", ""),
            card_data.get("type_line", ""),
            lang,
            api_key,
        )
        if t_card:
            card_data["printed_name"] = t_card.get("printed_name")
            card_data["printed_type_line"] = t_card.get("printed_type_line")
            card_data["printed_text"] = t_card.get("printed_text")


def _derive_text_source(card_data: dict, lang: str) -> str:
    """Infers text provenance for a cached card lacking a stored ``_text_source``."""
    if lang == "en":
        return "official"
    if is_text_untranslated(card_data):
        return "english"
    return "official"


def fetch_card_data(card_name: str, lang: str, cache, api_key: str = None) -> dict:
    """Fetches card data from cache or Scryfall, with set, language, and Gemini fallbacks.

    ``cache`` is a cache backend (see ``caching.file_cache.FileCardCache`` or
    ``caching.db_cache.DbCardCache``) exposing ``get_card``/``set_card``/
    ``has_image``/``get_image``/``set_image``.
    """
    slug = get_card_slug(card_name)
    cache_key = f"card_{lang}_{slug}"

    # 1. Check the cache.
    cached = cache.get_card(cache_key)
    if cached is not None:
        if cached.get("error") == "not_found":
            return None
        # If the cached entry is still untranslated (e.g. it was cached
        # without a Gemini key) and a key is now available, translate it
        # and refresh the cache so the language is honored.
        if lang != "en" and is_text_untranslated(cached):
            if api_key or os.environ.get("GEMINI_API_KEY"):
                _translate_card_data(cached, lang, api_key)
                cached["_text_source"] = "machine"
                cache.set_card(cache_key, cached)
        # Backfill provenance for entries cached before this field existed.
        if "_text_source" not in cached:
            cached["_text_source"] = _derive_text_source(cached, lang)
        return process_cached_card(cached, cache)

    # 2. Fetch from the Scryfall API.
    # 2a. Look up the exact English match first.
    encoded_name = urllib.parse.quote(card_name)
    exact_url = f"https://api.scryfall.com/cards/named?exact={encoded_name}"

    resp = _scryfall_get(exact_url)
    if resp is None:
        # Network/rate-limit gave up: do not cache, so it is retried next run.
        return None
    if resp.status_code != 200:
        if resp.status_code == 404:
            # Cache the negative result (the card genuinely does not exist).
            cache.set_card(cache_key, {"error": "not_found"})
        return None
    try:
        eng_card = resp.json()
    except Exception:
        return None

    # If English is requested, we are done.
    if lang == "en":
        eng_card["_text_source"] = "official"
        cache.set_card(cache_key, eng_card)
        return process_cached_card(eng_card, cache)

    # 2b. Attempt a localized lookup for the exact print.
    card_data = eng_card
    need_search_fallback = True

    set_code = eng_card.get("set")
    col_num = eng_card.get("collector_number")
    lang_url = f"https://api.scryfall.com/cards/{set_code}/{col_num}/{lang}"

    lang_resp = _scryfall_get(lang_url)
    if lang_resp is not None and lang_resp.status_code == 200:
        try:
            candidate = lang_resp.json()
            # Verify it has localized text.
            if not is_text_untranslated(candidate):
                card_data = candidate
                need_search_fallback = False
        except Exception:
            pass

    if need_search_fallback:
        # 2c. Fallback: search this name in this language across other sets (unique=prints).
        encoded_query = urllib.parse.quote(f'!"{eng_card.get("name")}" lang:{lang}')
        search_url = f"https://api.scryfall.com/cards/search?q={encoded_query}&unique=prints"
        search_resp = _scryfall_get(search_url)
        if search_resp is not None and search_resp.status_code == 200:
            try:
                search_json = search_resp.json()
                if "data" in search_json and len(search_json["data"]) > 0:
                    card_data = find_best_translated_card(search_json["data"], lang)
            except Exception:
                pass  # Fall back to the English card.

    # Copy prices and CMC from the English version (localized prints often lack them).
    if "prices" not in card_data or not any(card_data.get("prices", {}).values()):
        card_data["prices"] = eng_card.get("prices", {})

    # If the text is still untranslated and we are not in English, try Gemini.
    translated_via_gemini = False
    if lang != "en" and is_text_untranslated(card_data):
        has_key = api_key or os.environ.get("GEMINI_API_KEY")
        if has_key:
            _translate_card_data(card_data, lang, api_key)
            translated_via_gemini = True

    # Record text provenance (this branch only runs for non-English requests).
    if translated_via_gemini:
        card_data["_text_source"] = "machine"
    elif is_text_untranslated(card_data):
        card_data["_text_source"] = "english"
    else:
        card_data["_text_source"] = "official"

    # Cache the JSON details.
    cache.set_card(cache_key, card_data)

    return process_cached_card(card_data, cache)
