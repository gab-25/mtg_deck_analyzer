"""Django views: server-rendered (Tailwind) front-end for the deck analyzer."""

import logging
import os
import tempfile
import threading

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


def _resolved_api_key() -> str | None:
    return os.environ.get("GEMINI_API_KEY")


def _default_lang() -> str:
    return normalize_lang(os.environ.get("DEFAULT_LANG", DEFAULT_LANG))


def _build_categories(stored_cards: list) -> list:
    """Groups stored cards by category into a template-friendly structure."""
    grouped = {cat: [] for cat in CATEGORY_ORDER}
    for item in stored_cards:
        grouped[classify_card(item["data"])].append(item)

    categories = []
    for cat in CATEGORY_ORDER:
        items = grouped[cat]
        if not items:
            continue
        cards = []
        for item in items:
            data = item["data"]
            qty = item["quantity"]
            price = data.get("price_eur", 0.0)
            cards.append(
                {
                    "quantity": qty,
                    "price": price,
                    "total_price": price * qty,
                    "images": image_urls(data),
                    "faces": data.get("faces", []),
                    "text_source": data.get("text_source"),
                }
            )
        categories.append(
            {
                "label": CATEGORY_LABELS.get(cat, cat),
                "count": sum(i["quantity"] for i in items),
                "cards": cards,
            }
        )
    return categories


def _create_context(**extra) -> dict:
    """Builds the context the deck-creation form renders with."""
    return {
        "languages": LANG_DISPLAY_NAMES,
        "default_lang": _default_lang(),
        **extra,
    }


def _run_analysis(deck_id: int, decklist: str, lang: str, api_key: str | None):
    """Runs the heavy analysis for ``deck_id`` and persists the outcome."""
    try:
        Deck.objects.filter(pk=deck_id).update(status=Deck.Status.PROCESSING)
        result = analyze_decklist(
            decklist, lang=lang, api_key=api_key, cache=DbCardCache()
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
    except Exception as exc:  # noqa: BLE001 - record any failure for the user.
        logger.exception("Deck analysis failed for deck %s", deck_id)
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


def _start_analysis(deck_id: int, decklist: str, lang: str, api_key: str | None):
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
    decks = Deck.objects.order_by("-created_at")
    if query:
        decks = decks.filter(name__icontains=query)

    # Whether any listed deck is still being analyzed; drives the HTMX polling.
    has_processing = decks.filter(
        status__in=[Deck.Status.PENDING, Deck.Status.PROCESSING]
    ).exists()

    context = {"decks": decks, "query": query, "has_processing": has_processing}
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
def deck_detail(request, deck_id: int):
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

    return render(
        request,
        "deck.html",
        {
            "deck": deck,
            "lang_display": LANG_DISPLAY_NAMES.get(deck.lang, deck.lang),
            "categories": _build_categories(deck.cards or []),
            "analysis_html": analysis_html,
        },
    )


@login_required
@require_http_methods(["POST"])
def delete_deck(request, deck_id: int):
    Deck.objects.filter(pk=deck_id).delete()
    return redirect("index")


@login_required
@require_http_methods(["GET"])
def deck_pdf(request, deck_id: int):
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
