"""FastAPI application: HTMX + DaisyUI front-end for the deck analyzer."""

import os
import secrets
import tempfile
from contextlib import asynccontextmanager
from typing import Any, cast

import markdown as md
import requests
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

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


def is_zitadel_enabled() -> bool:
    return bool(
        os.environ.get("ZITADEL_CLIENT_ID") and os.environ.get("ZITADEL_DOMAIN")
    )


cast(Any, templates.env.globals)["is_zitadel_enabled"] = is_zitadel_enabled


class NotAuthenticatedException(Exception):
    pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="MTG Deck Analyzer", lifespan=lifespan)

app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SESSION_SECRET", "a-very-secret-key-change-me"),
    max_age=3600 * 24 * 7,  # 1 week session duration
)


@app.exception_handler(NotAuthenticatedException)
async def not_authenticated_handler(request: Request, exc: NotAuthenticatedException):
    target = "/auth/login"
    if request.headers.get("HX-Request"):
        return Response(status_code=204, headers={"HX-Redirect": target})
    return RedirectResponse(target, status_code=303)


def require_user(request: Request) -> dict[str, Any] | None:
    if not is_zitadel_enabled():
        return None
    user = request.session.get("user")
    if not user:
        raise NotAuthenticatedException()
    return user


def _resolved_api_key() -> str | None:
    return os.environ.get("GEMINI_API_KEY")


def _default_lang() -> str:
    return normalize_lang(os.environ.get("DEFAULT_LANG", DEFAULT_LANG))


def _build_categories(stored_cards: list[Any]) -> list[Any]:
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
    if is_zitadel_enabled() and not request.session.get("user"):
        return templates.TemplateResponse(request, "login.html")

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
    user: dict[str, Any] | None = Depends(require_user),
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
    deck_id: int,
    request: Request,
    session: Session = Depends(get_session),
    user: dict[str, Any] | None = Depends(require_user),
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
def deck_pdf(
    deck_id: int,
    session: Session = Depends(get_session),
    user: dict[str, Any] | None = Depends(require_user),
):
    deck = session.get(Deck, deck_id)
    if deck is None:
        raise HTTPException(status_code=404, detail="Deck not found")

    processed = cards_for_pdf(deck.cards or [], DbCardCache(session))

    fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    generate_pdf(deck.name, deck.analysis_md or "", processed, tmp_path)

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
def delete_deck(
    deck_id: int,
    session: Session = Depends(get_session),
    user: dict[str, Any] | None = Depends(require_user),
):
    deck = session.get(Deck, deck_id)
    if deck is not None:
        session.delete(deck)
        session.commit()
    # Empty body removes the row from the HTMX-managed list.
    return Response(status_code=200)


@app.get("/auth/login")
def auth_login(request: Request):
    if not is_zitadel_enabled():
        return RedirectResponse("/", status_code=303)

    domain = os.environ["ZITADEL_DOMAIN"].rstrip("/")
    if not domain.startswith(("http://", "https://")):
        domain = f"https://{domain}"

    client_id = os.environ["ZITADEL_CLIENT_ID"]
    redirect_uri = os.environ.get("ZITADEL_REDIRECT_URI")
    if not redirect_uri:
        redirect_uri = str(request.url_for("auth_callback"))

    state = secrets.token_urlsafe(16)
    request.session["oauth_state"] = state

    authorization_url = (
        f"{domain}/oauth/v2/authorize"
        f"?client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope=openid+profile+email"
        f"&state={state}"
    )
    return RedirectResponse(authorization_url, status_code=303)


@app.get("/auth/callback")
def auth_callback(request: Request):
    if not is_zitadel_enabled():
        return RedirectResponse("/", status_code=303)

    code = request.query_params.get("code")
    state = request.query_params.get("state")

    saved_state = request.session.pop("oauth_state", None)
    if not code or (saved_state and state != saved_state):
        raise HTTPException(status_code=400, detail="Invalid state or missing code")

    internal_domain = (
        os.environ.get("ZITADEL_INTERNAL_DOMAIN") or os.environ["ZITADEL_DOMAIN"]
    )
    internal_domain = internal_domain.rstrip("/")
    if not internal_domain.startswith(("http://", "https://")):
        internal_domain = f"https://{internal_domain}"

    client_id = os.environ["ZITADEL_CLIENT_ID"]
    client_secret = os.environ.get("ZITADEL_CLIENT_SECRET")
    redirect_uri = os.environ.get("ZITADEL_REDIRECT_URI")
    if not redirect_uri:
        redirect_uri = str(request.url_for("auth_callback"))

    # Exchange code for token
    token_url = f"{internal_domain}/oauth/v2/token"
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
    }
    if client_secret:
        data["client_secret"] = client_secret

    try:
        response = requests.post(token_url, data=data, timeout=10)
        response.raise_for_status()
        token_data = response.json()
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Failed to exchange token: {str(e)}"
        )

    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="No access token returned")

    # Fetch user info
    userinfo_url = f"{internal_domain}/oauth/v2/userinfo"
    try:
        userinfo_response = requests.get(
            userinfo_url,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        userinfo_response.raise_for_status()
        user_info = userinfo_response.json()
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Failed to fetch userinfo: {str(e)}"
        )

    request.session["user"] = user_info
    return RedirectResponse("/", status_code=303)


@app.get("/auth/logout")
def auth_logout(request: Request):
    request.session.pop("user", None)
    request.session.clear()
    return RedirectResponse("/", status_code=303)
