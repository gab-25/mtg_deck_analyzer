"""Django views: server-rendered (Tailwind) front-end for the deck analyzer."""

import os
import tempfile

import markdown as md
from django.contrib.auth.decorators import login_required
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
from .domain.storage import cards_for_pdf, cards_for_storage, image_urls
from .domain.text_utils import slugify
from .models import Deck
from .pipeline import analyze_decklist
from .rendering.pdf import generate_pdf

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


def _index_context(**extra) -> dict:
    """Builds the context the index page (and create errors) render with."""
    return {
        "decks": Deck.objects.order_by("-created_at"),
        "languages": LANG_DISPLAY_NAMES,
        "default_lang": _default_lang(),
        "has_api_key": bool(_resolved_api_key()),
        **extra,
    }


@login_required
@require_http_methods(["GET"])
def index(request):
    return render(request, "index.html", _index_context())


@login_required
@require_http_methods(["POST"])
def create_deck(request):
    name = (request.POST.get("name") or "").strip() or "Untitled Deck"
    decklist = request.POST.get("decklist", "")
    lang = normalize_lang(request.POST.get("lang", "en"))
    skip_analysis = request.POST.get("skip_analysis") in {"true", "on", "1"}

    try:
        result = analyze_decklist(
            decklist,
            lang=lang,
            api_key=_resolved_api_key(),
            cache=DbCardCache(),
            skip_analysis=skip_analysis,
        )
    except ValueError as e:
        # Re-render the form with the error and the user's input preserved.
        return render(
            request,
            "index.html",
            _index_context(
                error=str(e), form_name=name, form_decklist=decklist
            ),
            status=422,
        )

    stats = result["stats"]
    deck = Deck.objects.create(
        name=name,
        lang=lang,
        raw_decklist=decklist,
        analysis_md=result["deck_analysis"],
        deck_type=stats["deck_type"],
        total_cards=stats["total_cards"],
        total_value_eur=stats["total_value_eur"],
        avg_cmc=stats["avg_cmc"],
        category_counts=stats["category_counts"],
        cards=cards_for_storage(result["processed_cards"]),
    )

    # Post/Redirect/Get: send the browser to the new deck's detail page.
    return redirect("deck_detail", deck_id=deck.id)


@login_required
@require_http_methods(["GET"])
def deck_detail(request, deck_id: int):
    deck = get_object_or_404(Deck, pk=deck_id)

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
