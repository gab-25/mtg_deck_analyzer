"""Integration tests for the Django web service (hermetic, no network)."""

import pytest


def _fake_analyze(decklist, lang="en", api_key=None, skip_analysis=False, **kwargs):
    """Deterministic stand-in for the heavy analysis pipeline."""
    if not decklist.strip():
        raise ValueError("No cards could be parsed from the decklist.")
    return {
        "processed_cards": [
            {
                "quantity": 2,
                "data": {
                    "name": "Forest",
                    "type_line": "Basic Land — Forest",
                    "cmc": 0.0,
                    "price_eur": 0.05,
                    "image_paths": [],
                    "faces": [
                        {
                            "name": "Forest",
                            "mana_cost": "",
                            "type_line": "Basic Land — Forest",
                            "rules_text": "({T}: Add {G}.)",
                        }
                    ],
                },
            }
        ],
        "deck_analysis": None
        if skip_analysis
        else "## Overview\n\n- A **Forest** deck.",
        "name_map": {},
        "stats": {
            "deck_type": "Custom",
            "total_cards": 2,
            "total_value_eur": 0.10,
            "avg_cmc": 0.0,
            "category_counts": {"Land": 2},
        },
    }


@pytest.fixture
def client(client, monkeypatch):
    # Replace the heavy analysis pipeline with a deterministic stub.
    from mtg_deck_analyzer import views

    monkeypatch.setattr(views, "analyze_decklist", _fake_analyze)
    return client


@pytest.mark.django_db
def test_index_renders(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Analyze a deck" in r.content.decode()


@pytest.mark.django_db
def test_create_view_and_delete_deck(client):
    r = client.post(
        "/decks",
        data={"name": "Mono Green", "decklist": "2 Forest", "lang": "en"},
        HTTP_HX_REQUEST="true",
    )
    assert r.status_code == 204
    target = r["HX-Redirect"]

    detail = client.get(target)
    assert detail.status_code == 200
    body = detail.content.decode()
    assert "Mono Green" in body
    assert "Card List" in body
    assert "Lands" in body
    # The analysis Markdown is rendered to HTML.
    assert "Overview" in body

    # Listed on the index.
    assert "Mono Green" in client.get("/").content.decode()

    deck_id = target.rsplit("/", 1)[-1]
    assert client.delete(f"/decks/{deck_id}").status_code == 200
    assert client.get(target).status_code == 404


@pytest.mark.django_db
def test_create_with_empty_decklist_returns_error(client):
    r = client.post(
        "/decks",
        data={"name": "x", "decklist": "   ", "lang": "en"},
        HTTP_HX_REQUEST="true",
    )
    assert r.status_code == 422
    assert "alert-error" in r.content.decode()


@pytest.mark.django_db
def test_unknown_deck_returns_404(client):
    assert client.get("/decks/9999").status_code == 404


@pytest.mark.django_db
def test_pdf_download(client):
    r = client.post(
        "/decks",
        data={"name": "Mono Green", "decklist": "2 Forest", "lang": "en"},
        HTTP_HX_REQUEST="true",
    )
    deck_id = r["HX-Redirect"].rsplit("/", 1)[-1]
    pdf = client.get(f"/decks/{deck_id}/pdf")
    assert pdf.status_code == 200
    assert pdf["content-type"] == "application/pdf"
    assert b"".join(pdf.streaming_content).startswith(b"%PDF")


@pytest.mark.django_db
def test_media_route_serves_cached_image_from_db(client):
    from mtg_deck_analyzer.models import ScryfallImage

    # Missing image -> 404.
    assert client.get("/media/img_missing.jpg").status_code == 404

    # Seed an image directly into the cache table, then fetch it via /media.
    ScryfallImage.objects.create(name="img_seed.jpg", data=b"\x01\x02\x03")

    r = client.get("/media/img_seed.jpg")
    assert r.status_code == 200
    assert r["content-type"] == "image/jpeg"
    assert r.content == b"\x01\x02\x03"


@pytest.mark.django_db
def test_machine_translation_badge_shown(client):
    from mtg_deck_analyzer.models import Deck

    deck = Deck.objects.create(
        name="Tradotto",
        lang="it",
        raw_decklist="1 Forest",
        analysis_md=None,
        deck_type="Custom",
        total_cards=1,
        total_value_eur=0.0,
        avg_cmc=0.0,
        category_counts={"Land": 1},
        cards=[
            {
                "quantity": 1,
                "data": {
                    "name": "Foresta",
                    "type_line": "Basic Land — Forest",
                    "cmc": 0.0,
                    "price_eur": 0.0,
                    "image_paths": [],
                    "text_source": "machine",
                    "faces": [
                        {
                            "name": "Foresta",
                            "mana_cost": "",
                            "type_line": "Terra",
                            "rules_text": "({T}: Aggiungi {G}.)",
                        }
                    ],
                },
            }
        ],
    )

    r = client.get(f"/decks/{deck.id}")
    assert r.status_code == 200
    assert "Auto-translated" in r.content.decode()
