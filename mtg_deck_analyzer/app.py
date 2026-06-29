"""FastAPI application: HTMX + DaisyUI front-end for the deck analyzer."""

import os
import tempfile
from contextlib import asynccontextmanager

import markdown as md
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from .cards import classify_card
from .constants import (
    CATEGORY_ORDER,
    DEFAULT_LANG,
    LANG_DISPLAY_NAMES,
    normalize_lang,
)
from .db import get_session, init_db
from .db_cache import DbCardCache
from .models import Deck
from .pdf import generate_pdf
from .service import analyze_decklist
from .storage import cards_for_pdf, cards_for_storage, image_urls
from .text_utils import slugify

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

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

templates = Jinja2Templates(directory=TEMPLATES_DIR)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="MTG Deck Analyzer", lifespan=lifespan)


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


@app.get("/", response_class=HTMLResponse)
def index(request: Request, session: Session = Depends(get_session)):
    decks = (
        session.execute(select(Deck).order_by(Deck.created_at.desc())).scalars().all()
    )
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "decks": decks,
            "languages": LANG_DISPLAY_NAMES,
            "default_lang": _default_lang(),
            "has_api_key": bool(_resolved_api_key()),
        },
    )


@app.post("/decks")
def create_deck(
    request: Request,
    name: str = Form(...),
    decklist: str = Form(...),
    lang: str = Form("en"),
    skip_analysis: bool = Form(False),
    session: Session = Depends(get_session),
):
    name = name.strip() or "Untitled Deck"
    lang = normalize_lang(lang)

    try:
        result = analyze_decklist(
            decklist,
            lang=lang,
            api_key=_resolved_api_key(),
            cache=DbCardCache(session),
            skip_analysis=skip_analysis,
        )
    except ValueError as e:
        return templates.TemplateResponse(
            request,
            "partials/form_error.html",
            {"error": str(e)},
            status_code=422,
        )

    stats = result["stats"]
    deck = Deck(
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
    session.add(deck)
    session.commit()
    session.refresh(deck)

    target = f"/decks/{deck.id}"
    # HTMX expects a redirect via header so it swaps the whole page location.
    if request.headers.get("HX-Request"):
        return Response(status_code=204, headers={"HX-Redirect": target})
    return RedirectResponse(target, status_code=303)


@app.get("/decks/{deck_id}", response_class=HTMLResponse)
def deck_detail(
    deck_id: int, request: Request, session: Session = Depends(get_session)
):
    deck = session.get(Deck, deck_id)
    if deck is None:
        raise HTTPException(status_code=404, detail="Deck not found")

    analysis_html = None
    if deck.analysis_md:
        analysis_html = md.markdown(
            deck.analysis_md, extensions=["extra", "sane_lists"]
        )

    return templates.TemplateResponse(
        request,
        "deck.html",
        {
            "deck": deck,
            "lang_display": LANG_DISPLAY_NAMES.get(deck.lang, deck.lang),
            "categories": _build_categories(deck.cards or []),
            "analysis_html": analysis_html,
        },
    )


@app.get("/decks/{deck_id}/pdf")
def deck_pdf(deck_id: int, session: Session = Depends(get_session)):
    deck = session.get(Deck, deck_id)
    if deck is None:
        raise HTTPException(status_code=404, detail="Deck not found")

    processed = cards_for_pdf(deck.cards or [], DbCardCache(session))

    fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    generate_pdf(deck.name, deck.analysis_md, processed, tmp_path)

    filename = f"{slugify(deck.name) or 'deck'}.pdf"
    return FileResponse(tmp_path, media_type="application/pdf", filename=filename)


@app.get("/media/{name}")
def media(name: str, session: Session = Depends(get_session)):
    """Serves a cached card image from the database."""
    data = DbCardCache(session).get_image(name)
    if data is None:
        raise HTTPException(status_code=404, detail="Image not found")
    return Response(content=data, media_type="image/jpeg")


@app.delete("/decks/{deck_id}")
def delete_deck(deck_id: int, session: Session = Depends(get_session)):
    deck = session.get(Deck, deck_id)
    if deck is not None:
        session.delete(deck)
        session.commit()
    # Empty body removes the row from the HTMX-managed list.
    return Response(status_code=200)
