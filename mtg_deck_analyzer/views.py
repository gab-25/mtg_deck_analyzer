"""Django views: server-rendered (Tailwind) front-end for the deck analyzer."""

import logging
import os
import re
import tempfile
import threading
import uuid

import markdown as md
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .caching.db_cache import DbCardCache
from .domain.cards import classify_card
from .domain.constants import (
    CATEGORY_ORDER,
    DEFAULT_LANG,
    LANG_DISPLAY_NAMES,
    normalize_lang,
)
from .domain.decklist import parse_decklist_text
from .domain.storage import cards_for_pdf, cards_for_storage, image_urls
from .domain.text_utils import slugify
from .logging_context import deck_log_context
from .models import Deck
from .pipeline import analyze_decklist
from .rendering.pdf import generate_pdf

logger = logging.getLogger(__name__)

# Plural display labels for card categories (web shows them as section headers).
CATEGORY_LABELS = {
    "Creature": "Creatures",
    "Land": "Lands",
    "Planeswalker": "Planeswalkers",
    "Instant": "Instants",
    "Sorcery": "Sorceries",
    "Artifact": "Artifacts",
    "Enchantment": "Enchantments",
    "Battle": "Battles",
    "Other": "Other",
}

# WUBRG pip colors and per-category accent colors, mirroring the design mockup.
COLOR_HEX = {
    "W": "#f3ecd2",
    "U": "#4b8fd6",
    "B": "#7c6f86",
    "R": "#d05a3e",
    "G": "#4c9e6a",
    "C": "#b7b0a8",
}
TYPE_HEX = {
    "Creature": "#8fd08f",
    "Instant": "#7fb6e0",
    "Sorcery": "#c79be0",
    "Land": "#d6c08a",
    "Artifact": "#b7b0a8",
    "Enchantment": "#e0a8c8",
    "Planeswalker": "#e8b64c",
    "Battle": "#d05a3e",
    "Other": "#b7b0a8",
}

_MANA_SYMBOL_RE = re.compile(r"\{([^}]+)\}")


def _deck_pips(stored_cards: list) -> list:
    """Derives the deck's color identity from its cards' mana costs.

    Colors aren't stored on cards, so we scan the mana symbols of every face and
    collect the distinct WUBRG letters, returned in canonical WUBRG order. Falls
    back to a single colorless pip for lands-only / artifact decks.
    """
    found = set()
    for item in stored_cards:
        for face in item.get("data", {}).get("faces", []):
            for symbol in _MANA_SYMBOL_RE.findall(face.get("mana_cost", "") or ""):
                for ch in symbol:
                    if ch in "WUBRG":
                        found.add(ch)
    order = [c for c in "WUBRG" if c in found] or ["C"]
    return [{"letter": c, "hex": COLOR_HEX[c]} for c in order]


def _mana_curve(stored_cards: list) -> list:
    """Buckets non-land cards by mana value (0–6, then 7+), weighted by quantity."""
    buckets = [0] * 8  # indices 0..6 exact, 7 => "7+"
    for item in stored_cards:
        data = item["data"]
        if classify_card(data) == "Land":
            continue
        idx = min(int(data.get("cmc", 0) or 0), 7)
        buckets[idx] += item["quantity"]
    peak = max(buckets) or 1
    labels = ["0", "1", "2", "3", "4", "5", "6", "7+"]
    return [
        {"label": labels[i], "count": buckets[i], "pct": round(buckets[i] / peak * 100)}
        for i in range(8)
    ]


def _type_bars(category_counts: dict) -> list:
    """Turns the stored category counts into proportional bars for the sidebar."""
    total = sum(category_counts.values()) or 1
    bars = []
    for cat in CATEGORY_ORDER:
        count = category_counts.get(cat, 0)
        if not count:
            continue
        bars.append(
            {
                "label": CATEGORY_LABELS.get(cat, cat),
                "count": count,
                "hex": TYPE_HEX.get(cat, "#b7b0a8"),
                "pct": round(count / total * 100),
            }
        )
    return bars


def _value_stats(stored_cards: list, total_value: float) -> dict:
    """Value summary for the sidebar: total, average per card and most expensive."""
    prices = [item["data"].get("price_eur", 0.0) for item in stored_cards]
    total_cards = sum(item["quantity"] for item in stored_cards) or 1
    return {
        "total": total_value,
        "avg": total_value / total_cards,
        "max": max(prices) if prices else 0.0,
    }


def _detail_card_groups(stored_cards: list) -> list:
    """Groups cards by category into row view-models for the deck detail page."""
    grouped = {cat: [] for cat in CATEGORY_ORDER}
    for item in stored_cards:
        grouped[classify_card(item["data"])].append(item)

    groups = []
    for cat in CATEGORY_ORDER:
        items = grouped[cat]
        if not items:
            continue
        cards = []
        for item in items:
            data = item["data"]
            faces = data.get("faces", [])
            oracle = "\n".join(
                f.get("rules_text", "") for f in faces if f.get("rules_text")
            )
            urls = image_urls(data)
            paths = data.get("image_paths", [])
            price = data.get("price_eur", 0.0)
            cards.append(
                {
                    "name": data.get("name", ""),
                    "type": cat,
                    "type_hex": TYPE_HEX.get(cat, "#b7b0a8"),
                    "mv": int(data.get("cmc", 0) or 0),
                    "oracle": oracle,
                    "price": price,
                    "quantity": item["quantity"],
                    "image": urls[0] if urls else "",
                    "image_name": paths[0] if paths else "",
                    "text_source": data.get("text_source"),
                }
            )
        groups.append(
            {
                "label": CATEGORY_LABELS.get(cat, cat),
                "hex": TYPE_HEX.get(cat, "#b7b0a8"),
                "count": sum(i["quantity"] for i in items),
                "cards": cards,
            }
        )
    return groups


def _resolved_api_key() -> str | None:
    return os.environ.get("GEMINI_API_KEY")


def _default_lang() -> str:
    return normalize_lang(os.environ.get("DEFAULT_LANG", DEFAULT_LANG))


def _create_context(**extra) -> dict:
    """Builds the context the deck-creation form renders with."""
    return {
        "languages": LANG_DISPLAY_NAMES,
        "default_lang": _default_lang(),
        **extra,
    }


def _run_analysis(deck_id: uuid.UUID, decklist: str, lang: str, api_key: str | None):
    """Runs the heavy analysis for ``deck_id`` and persists the outcome.

    Binds the deck id to the logging context so every record emitted during the
    run — including those from the pipeline/Scryfall/Gemini modules — is stamped
    with ``[deck <id>]``.
    """
    with deck_log_context(deck_id):
        try:
            Deck.objects.filter(pk=deck_id).update(status=Deck.Status.PROCESSING)
            result = analyze_decklist(
                decklist,
                lang=lang,
                api_key=api_key,
                cache=DbCardCache(),
                progress=lambda msg: logger.info("%s", msg),
            )
            stats = result["stats"]
            Deck.objects.filter(pk=deck_id).update(
                analysis_md=result["deck_analysis"],
                deck_type=stats["deck_type"],
                total_cards=stats["total_cards"],
                total_value_eur=stats["total_value_eur"],
                avg_cmc=stats["avg_cmc"],
                category_counts=stats["category_counts"],
                cards=cards_for_storage(result["processed_cards"]),
                status=Deck.Status.READY,
                error=None,
            )
            logger.info(
                "Deck analysis completed (%s cards, type %s)",
                stats["total_cards"],
                stats["deck_type"],
            )
        except Exception as exc:  # noqa: BLE001 - record any failure for the user.
            logger.exception("Deck analysis failed")
            Deck.objects.filter(pk=deck_id).update(
                status=Deck.Status.FAILED, error=str(exc)
            )


def _run_analysis_threaded(deck_id, decklist, lang, api_key):
    """Thread entry point: runs the analysis, then releases the DB connection.

    The background thread gets its own connection from Django's thread-local
    pool; close it on the way out so it isn't left dangling.
    """
    try:
        _run_analysis(deck_id, decklist, lang, api_key)
    finally:
        connection.close()


def _start_analysis(deck_id: uuid.UUID, decklist: str, lang: str, api_key: str | None):
    """Kicks off the analysis, in a background thread unless disabled (tests)."""
    if getattr(settings, "ASYNC_DECK_ANALYSIS", True):
        threading.Thread(
            target=_run_analysis_threaded,
            args=(deck_id, decklist, lang, api_key),
            daemon=True,
        ).start()
    else:
        _run_analysis(deck_id, decklist, lang, api_key)


@login_required
@require_http_methods(["GET"])
def index(request):
    query = (request.GET.get("q") or "").strip()
    decks = list(Deck.objects.order_by("-created_at"))
    if query:
        needle = query.lower()
        decks = [d for d in decks if needle in d.name.lower()]

    # Annotate each deck with its color pips for the list cards.
    for deck in decks:
        deck.pips = _deck_pips(deck.cards or [])

    # Whether any listed deck is still being analyzed; drives the HTMX polling.
    has_processing = any(
        d.status in {Deck.Status.PENDING, Deck.Status.PROCESSING} for d in decks
    )

    # Library-wide stats for the header cards (independent of the search filter).
    all_decks = Deck.objects.all()
    stat_total = all_decks.count()
    stat_analyzed = all_decks.filter(status=Deck.Status.READY).count()
    stat_value = sum(d.total_value_eur for d in all_decks)

    context = {
        "decks": decks,
        "query": query,
        "has_processing": has_processing,
        "stat_total": stat_total,
        "stat_analyzed": stat_analyzed,
        "stat_value": stat_value,
    }
    # HTMX poll: return just the list region so it can swap itself in place.
    template = "partials/deck_list.html" if request.htmx else "index.html"
    return render(request, template, context)


@login_required
@require_http_methods(["GET"])
def new_deck(request):
    return render(request, "create.html", _create_context())


@login_required
@require_http_methods(["POST"])
def create_deck(request):
    name = (request.POST.get("name") or "").strip() or "Untitled Deck"
    decklist = request.POST.get("decklist", "")
    lang = normalize_lang(request.POST.get("lang", "en"))

    # Cheap, synchronous validation so obvious mistakes are reported inline; the
    # multi-minute Scryfall + Gemini work happens in the background afterwards.
    if not parse_decklist_text(decklist):
        return render(
            request,
            "create.html",
            _create_context(
                error="No cards could be parsed from the decklist.",
                form_name=name,
                form_decklist=decklist,
            ),
            status=422,
        )

    deck = Deck.objects.create(
        name=name,
        lang=lang,
        raw_decklist=decklist,
        status=Deck.Status.PENDING,
    )
    _start_analysis(deck.id, decklist, lang, _resolved_api_key())

    # Post/Redirect/Get: back to the deck list, where the new deck shows an
    # "Analyzing…" status and the list polls itself until it's ready.
    return redirect("index")


@login_required
@require_http_methods(["GET"])
def deck_detail(request, deck_id: uuid.UUID):
    deck = get_object_or_404(Deck, pk=deck_id)

    # While the analysis is still running there's nothing to show yet — send the
    # user to the list, where the deck displays its live "Analyzing…" status.
    if deck.status in {Deck.Status.PENDING, Deck.Status.PROCESSING}:
        return redirect("index")
    if deck.status == Deck.Status.FAILED:
        return render(request, "deck_failed.html", {"deck": deck})

    analysis_html = None
    if deck.analysis_md:
        analysis_html = md.markdown(
            deck.analysis_md, extensions=["extra", "sane_lists"]
        )

    stored_cards = deck.cards or []
    return render(
        request,
        "deck.html",
        {
            "deck": deck,
            "lang_display": LANG_DISPLAY_NAMES.get(deck.lang, deck.lang),
            "analysis_html": analysis_html,
            "pips": _deck_pips(stored_cards),
            "card_groups": _detail_card_groups(stored_cards),
            "mana_curve": _mana_curve(stored_cards),
            "type_bars": _type_bars(deck.category_counts or {}),
            "value_stats": _value_stats(stored_cards, deck.total_value_eur),
        },
    )


@login_required
@require_http_methods(["GET"])
def edit_deck(request, deck_id: uuid.UUID):
    deck = get_object_or_404(Deck, pk=deck_id)
    return render(
        request,
        "edit.html",
        _create_context(
            deck=deck,
            form_name=deck.name,
            form_decklist=deck.raw_decklist,
            default_lang=deck.lang,
        ),
    )


@login_required
@require_http_methods(["POST"])
def update_deck(request, deck_id: uuid.UUID):
    deck = get_object_or_404(Deck, pk=deck_id)
    name = (request.POST.get("name") or "").strip() or "Untitled Deck"
    decklist = request.POST.get("decklist", "")
    lang = normalize_lang(request.POST.get("lang", "en"))

    if not parse_decklist_text(decklist):
        return render(
            request,
            "edit.html",
            _create_context(
                deck=deck,
                error="No cards could be parsed from the decklist.",
                form_name=name,
                form_decklist=decklist,
                default_lang=lang,
            ),
            status=422,
        )

    # Only the decklist and language feed the analysis; re-run it just when one of
    # those actually changed, so a plain rename doesn't trigger minutes of work.
    needs_reanalysis = decklist != deck.raw_decklist or lang != deck.lang

    deck.name = name
    deck.raw_decklist = decklist
    deck.lang = lang
    if needs_reanalysis:
        deck.status = Deck.Status.PENDING
        deck.error = None
    deck.save()

    if needs_reanalysis:
        _start_analysis(deck.id, decklist, lang, _resolved_api_key())
        return redirect("index")
    return redirect("deck_detail", deck_id=deck.id)


@login_required
@require_http_methods(["POST"])
def reanalyze_deck(request, deck_id: uuid.UUID):
    """Re-runs the analysis for an existing deck from its stored decklist."""
    deck = get_object_or_404(Deck, pk=deck_id)
    deck.status = Deck.Status.PENDING
    deck.error = None
    deck.save(update_fields=["status", "error"])
    _start_analysis(deck.id, deck.raw_decklist, deck.lang, _resolved_api_key())

    # Back to the list, where the deck shows its live "Analyzing…" status and the
    # list polls itself until the re-analysis is done.
    return redirect("index")


@login_required
@require_http_methods(["POST"])
def delete_deck(request, deck_id: uuid.UUID):
    Deck.objects.filter(pk=deck_id).delete()
    return redirect("index")


@login_required
@require_http_methods(["GET"])
def deck_pdf(request, deck_id: uuid.UUID):
    deck = get_object_or_404(Deck, pk=deck_id)

    # The PDF needs the fetched cards; they only exist once analysis is done.
    if deck.status != Deck.Status.READY:
        return redirect("deck_detail", deck_id=deck.id)

    processed = cards_for_pdf(deck.cards or [], DbCardCache())

    fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    generate_pdf(deck.name, deck.analysis_md, processed, tmp_path)

    filename = f"{slugify(deck.name) or 'deck'}.pdf"
    return FileResponse(
        open(tmp_path, "rb"),
        content_type="application/pdf",
        as_attachment=True,
        filename=filename,
    )


@login_required
@require_http_methods(["GET"])
def media(request, name: str):
    """Serves a cached card image from the database."""
    data = DbCardCache().get_image(name)
    if data is None:
        return HttpResponse("Image not found", status=404)
    return HttpResponse(data, content_type="image/jpeg")


@login_required
@require_http_methods(["GET"])
def card_image_modal(request):
    """Returns the zoom-modal fragment for one cached card image (HTMX).

    The thumbnail buttons in the deck view ``hx-get`` this endpoint with the
    image basename; the fragment is a full-screen CSS overlay carrying the
    full-size image. Called without a ``name`` it returns an empty body, which
    the overlay uses to close itself (clicking it clears the container).
    """
    name = request.GET.get("name", "")
    if not name:
        return HttpResponse("")  # Close: clear the modal container.
    if DbCardCache().get_image(name) is None:
        return HttpResponse("Image not found", status=404)
    return render(request, "partials/card_image_modal.html", {"image_url": f"/media/{name}"})
