"""Integration tests for the Django web service (hermetic, no network)."""

import pytest
from django.utils.html import escape

COMMANDER = "Atraxa, Praetors' Voice"


def _legal_decklist(commander=COMMANDER):
    """A 100-card singleton Commander decklist the creation form accepts."""
    lines = ["Commander", f"1 {commander}", "", "Deck"]
    lines += [f"1 Spell {i}" for i in range(60)]
    lines.append("39 Forest")
    return "\n".join(lines)


def _fake_analyze(decklist, api_key=None, skip_analysis=False, **kwargs):
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
        "stats": {
            "commanders": [COMMANDER],
            "color_identity": ["W", "U", "B", "G"],
            "total_cards": 2,
            "total_value_eur": 0.10,
            "avg_cmc": 0.0,
            "category_counts": {"Land": 2},
        },
    }


@pytest.fixture
def client(client, monkeypatch, django_user_model):
    # Replace the heavy analysis pipeline with a deterministic stub.
    from mtg_deck_analyzer import views

    monkeypatch.setattr(views, "analyze_decklist", _fake_analyze)
    # Every app view requires authentication; log in a throwaway user.
    user = django_user_model.objects.create_user(username="tester", password="pw")
    client.force_login(user)
    return client


@pytest.mark.django_db
def test_protected_view_redirects_to_login_when_anonymous(client):
    client.logout()
    r = client.get("/")
    assert r.status_code == 302
    assert r["Location"].startswith("/login")


@pytest.mark.django_db
def test_login_page_renders(client):
    client.logout()
    r = client.get("/login")
    assert r.status_code == 200
    assert "Sign in" in r.content.decode()


@pytest.mark.django_db
def test_index_renders(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Your Decks" in r.content.decode()


@pytest.mark.django_db
def test_create_page_renders_form(client):
    r = client.get("/decks/new")
    assert r.status_code == 200
    assert "Analyze a deck" in r.content.decode()


@pytest.mark.django_db
def test_index_search_filters_by_name(client):
    from mtg_deck_analyzer.models import Deck

    Deck.objects.create(name="Mono Green", raw_decklist="1 Forest")
    Deck.objects.create(name="Mono Red", raw_decklist="1 Mountain")

    body = client.get("/", {"q": "green"}).content.decode()
    assert "Mono Green" in body
    assert "Mono Red" not in body


@pytest.mark.django_db
def test_create_view_and_delete_deck(client):
    from mtg_deck_analyzer.models import Deck

    r = client.post(
        "/decks",
        data={"name": "Mono Green", "decklist": _legal_decklist()},
    )
    # Post/Redirect/Get back to the deck list.
    assert r.status_code == 302
    assert r["Location"] == "/"

    # Analysis runs inline in tests, so the deck is ready immediately.
    deck = Deck.objects.get(name="Mono Green")
    assert deck.status == Deck.Status.READY

    detail = client.get(f"/decks/{deck.id}")
    assert detail.status_code == 200
    body = detail.content.decode()
    assert "Mono Green" in body
    assert "Cards" in body
    assert "Lands" in body
    # The analysis Markdown is rendered to HTML.
    assert "Overview" in body

    # Listed on the index.
    assert "Mono Green" in client.get("/").content.decode()

    delete = client.post(f"/decks/{deck.id}/delete")
    assert delete.status_code == 302
    assert client.get(f"/decks/{deck.id}").status_code == 404


@pytest.mark.django_db
def test_create_with_empty_decklist_returns_error(client):
    r = client.post(
        "/decks",
        data={"name": "x", "decklist": "   "},
    )
    assert r.status_code == 422
    assert "No cards could be parsed" in r.content.decode()


@pytest.mark.django_db
def test_create_rejects_a_deck_that_is_not_commander_legal(client):
    from mtg_deck_analyzer.models import Deck

    # A 60-card constructed pile: wrong size, no commander, playsets.
    decklist = "4 Lightning Bolt\n" + "\n".join(f"1 Spell {i}" for i in range(56))
    r = client.post("/decks", data={"name": "Standard Pile", "decklist": decklist})

    assert r.status_code == 422
    body = r.content.decode()
    # Every problem is listed at once, so the deck can be fixed in one pass.
    assert "60 cards" in body
    assert "No commander declared" in body
    assert "singleton" in body
    # Nothing illegal reaches the library.
    assert not Deck.objects.exists()


@pytest.mark.django_db
def test_edit_rejects_a_deck_that_is_not_commander_legal(client):
    from mtg_deck_analyzer.models import Deck

    deck = Deck.objects.create(name="Legal", raw_decklist=_legal_decklist())
    r = client.post(
        f"/decks/{deck.id}/update",
        data={"name": "Legal", "decklist": "1 Sol Ring"},
    )
    assert r.status_code == 422
    assert "1 cards" in r.content.decode()
    # The stored decklist is untouched.
    deck.refresh_from_db()
    assert deck.raw_decklist == _legal_decklist()


@pytest.mark.django_db
def test_pending_deck_redirects_to_index(client):
    from mtg_deck_analyzer.models import Deck

    deck = Deck.objects.create(
        name="In Progress",
        raw_decklist="1 Forest",
        status=Deck.Status.PROCESSING,
    )
    # No status page: the detail view sends in-progress decks back to the list.
    r = client.get(f"/decks/{deck.id}")
    assert r.status_code == 302
    assert r["Location"] == "/"


@pytest.mark.django_db
def test_index_shows_processing_status_and_polls(client):
    from mtg_deck_analyzer.models import Deck

    Deck.objects.create(
        name="In Progress",
        raw_decklist="1 Forest",
        status=Deck.Status.PROCESSING,
    )
    body = client.get("/").content.decode()
    assert "Analyzing" in body
    # The list region polls itself while something is still processing.
    assert 'hx-trigger="every' in body


@pytest.mark.django_db
def test_index_stops_polling_when_all_ready(client):
    from mtg_deck_analyzer.models import Deck

    Deck.objects.create(name="Done", raw_decklist="1 Forest", status=Deck.Status.READY)
    body = client.get("/").content.decode()
    assert "hx-trigger" not in body


@pytest.mark.django_db
def test_htmx_request_returns_list_fragment(client):
    from mtg_deck_analyzer.models import Deck

    Deck.objects.create(name="Solo", raw_decklist="1 Forest", status=Deck.Status.READY)
    r = client.get("/", HTTP_HX_REQUEST="true")
    body = r.content.decode()
    assert "Solo" in body
    # A fragment (the list region), not the whole page.
    assert "<!DOCTYPE html>" not in body
    assert 'id="deck-list-region"' in body


@pytest.mark.django_db
def test_failed_deck_shows_error_page(client):
    from mtg_deck_analyzer.models import Deck

    deck = Deck.objects.create(
        name="Broken",
        raw_decklist="1 Forest",
        status=Deck.Status.FAILED,
        error="Scryfall is unreachable.",
    )
    r = client.get(f"/decks/{deck.id}")
    assert r.status_code == 200
    body = r.content.decode()
    assert "Analysis failed" in body
    assert "Scryfall is unreachable." in body


@pytest.mark.django_db
def test_pdf_unavailable_until_ready(client):
    from mtg_deck_analyzer.models import Deck

    deck = Deck.objects.create(
        name="In Progress",
        raw_decklist="1 Forest",
        status=Deck.Status.PENDING,
    )
    r = client.get(f"/decks/{deck.id}/pdf")
    # Redirects back to the detail page instead of producing an empty PDF.
    assert r.status_code == 302
    assert r["Location"].endswith(f"/decks/{deck.id}")


@pytest.mark.django_db
def test_unknown_deck_returns_404(client):
    assert (
        client.get("/decks/00000000-0000-0000-0000-000000000000").status_code == 404
    )


@pytest.mark.django_db
def test_pdf_download(client):
    from mtg_deck_analyzer.models import Deck

    client.post(
        "/decks",
        data={"name": "Mono Green", "decklist": _legal_decklist()},
    )
    deck_id = Deck.objects.get(name="Mono Green").id
    pdf = client.get(f"/decks/{deck_id}/pdf")
    assert pdf.status_code == 200
    assert pdf["content-type"] == "application/pdf"
    assert b"".join(pdf.streaming_content).startswith(b"%PDF")


@pytest.mark.django_db
def test_proxy_pdf_unavailable_until_ready(client):
    from mtg_deck_analyzer.models import Deck

    deck = Deck.objects.create(
        name="In Progress",
        raw_decklist="1 Forest",
        status=Deck.Status.PENDING,
    )
    r = client.get(f"/decks/{deck.id}/proxy")
    assert r.status_code == 302
    assert r["Location"].endswith(f"/decks/{deck.id}")


@pytest.mark.django_db
def test_proxy_pdf_download(client):
    import io

    from PIL import Image

    from mtg_deck_analyzer.models import Deck, ScryfallImage

    # A real opaque JPEG so ReportLab can actually rasterize it into the PDF.
    buf = io.BytesIO()
    Image.new("RGB", (63, 88), (10, 120, 60)).save(buf, format="JPEG")
    ScryfallImage.objects.create(name="img_forest.jpg", data=buf.getvalue())

    deck = Deck.objects.create(
        name="Mono Green",
        raw_decklist="3 Forest",
        status=Deck.Status.READY,
        total_cards=3,
        total_value_eur=0.0,
        avg_cmc=0.0,
        category_counts={"Land": 3},
        cards=[
            {
                "quantity": 3,
                "data": {
                    "name": "Forest",
                    "type_line": "Basic Land — Forest",
                    "cmc": 0.0,
                    "price_eur": 0.0,
                    "image_paths": ["img_forest.jpg"],
                    "faces": [{"name": "Forest", "mana_cost": "", "type_line": "", "rules_text": ""}],
                },
            }
        ],
    )

    pdf = client.get(f"/decks/{deck.id}/proxy")
    assert pdf.status_code == 200
    assert pdf["content-type"] == "application/pdf"
    assert b"".join(pdf.streaming_content).startswith(b"%PDF")


@pytest.mark.django_db
def test_deck_detail_has_export_proxy_button(client):
    from mtg_deck_analyzer.models import Deck

    deck = Deck.objects.create(
        name="Proxy Me",
        raw_decklist="1 Forest",
        status=Deck.Status.READY,
        total_cards=1,
        total_value_eur=0.0,
        avg_cmc=0.0,
        category_counts={"Land": 1},
        cards=[],
    )
    body = client.get(f"/decks/{deck.id}").content.decode()
    assert f'href="/decks/{deck.id}/proxy"' in body
    assert "Export proxy" in body


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
def test_card_image_modal_returns_dialog_fragment(client):
    from mtg_deck_analyzer.models import ScryfallImage

    # Unknown image -> 404, so the modal never opens on a stale/bad name.
    assert client.get("/card-image", {"name": "img_missing.jpg"}).status_code == 404

    ScryfallImage.objects.create(name="img_seed.jpg", data=b"\x01\x02\x03")
    r = client.get("/card-image", {"name": "img_seed.jpg"})
    assert r.status_code == 200
    body = r.content.decode()
    # A CSS-overlay fragment carrying the full-size image — no inline JS.
    assert "<!DOCTYPE html>" not in body
    assert 'src="/media/img_seed.jpg"' in body
    assert "<script" not in body
    assert "onclick" not in body

    # No name -> empty body, which clears the container (closes the modal).
    close = client.get("/card-image")
    assert close.status_code == 200
    assert close.content.decode().strip() == ""


@pytest.mark.django_db
def test_deck_detail_card_images_link_to_modal(client):
    from mtg_deck_analyzer.models import Deck

    deck = Deck.objects.create(
        name="With Image",
        raw_decklist="1 Forest",
        status=Deck.Status.READY,
        total_cards=1,
        total_value_eur=0.0,
        avg_cmc=0.0,
        category_counts={"Land": 1},
        cards=[
            {
                "quantity": 1,
                "data": {
                    "name": "Forest",
                    "type_line": "Basic Land — Forest",
                    "cmc": 0.0,
                    "price_eur": 0.0,
                    "image_paths": ["img_forest.jpg"],
                    "faces": [{"name": "Forest", "mana_cost": "", "type_line": "", "rules_text": ""}],
                },
            }
        ],
    )

    body = client.get(f"/decks/{deck.id}").content.decode()
    # The thumbnail is an HTMX button that fetches the zoom modal.
    assert 'hx-get="/card-image?name=img_forest.jpg"' in body
    assert 'hx-target="#card-image-modal-container"' in body
    assert 'src="/media/img_forest.jpg"' in body


@pytest.mark.django_db
def test_deck_detail_and_list_show_the_commander(client):
    from mtg_deck_analyzer.models import Deck

    deck = Deck.objects.create(
        name="Atraxa Superfriends",
        raw_decklist=_legal_decklist(),
        status=Deck.Status.READY,
        commanders=[COMMANDER],
        color_identity=["W", "U", "B", "G"],
        total_cards=100,
        total_value_eur=0.0,
        avg_cmc=3.0,
        category_counts={"Creature": 1},
        cards=[
            {
                "quantity": 1,
                "is_commander": True,
                "data": {
                    "name": COMMANDER,
                    "type_line": "Legendary Creature — Phyrexian Angel Horror",
                    "cmc": 4.0,
                    "price_eur": 0.0,
                    "color_identity": ["W", "U", "B", "G"],
                    "image_paths": ["img_atraxa.jpg"],
                    "faces": [
                        {
                            "name": COMMANDER,
                            "mana_cost": "{G}{W}{U}{B}",
                            "type_line": "Legendary Creature — Phyrexian Angel Horror",
                            "rules_text": "Flying, vigilance, deathtouch, lifelink",
                        }
                    ],
                },
            }
        ],
    )

    # The name is rendered HTML-escaped (it carries an apostrophe).
    commander_html = escape(COMMANDER)

    detail = client.get(f"/decks/{deck.id}").content.decode()
    # The format chip is fixed, and the commander is named next to it.
    assert '<span class="chip">Commander</span>' in detail
    assert commander_html in detail
    # The commander panel carries the card art.
    assert 'src="/media/img_atraxa.jpg"' in detail

    listing = client.get("/").content.decode()
    assert '<span class="chip">Commander</span>' in listing
    assert commander_html in listing


@pytest.mark.django_db
def test_deck_detail_copy_plain_text_button(client):
    from mtg_deck_analyzer.models import Deck

    deck = Deck.objects.create(
        name="Copy Me",
        raw_decklist="4 Llanowar Elves\n2 Forest",
        status=Deck.Status.READY,
        total_cards=6,
        total_value_eur=0.0,
        avg_cmc=0.5,
        category_counts={"Creature": 4, "Land": 2},
        cards=[
            {
                "quantity": 4,
                "data": {
                    "name": "Llanowar Elves",
                    "type_line": "Creature — Elf Druid",
                    "cmc": 1.0,
                    "price_eur": 0.0,
                    "image_paths": [],
                    "faces": [{"name": "Llanowar Elves", "mana_cost": "{G}", "type_line": "", "rules_text": ""}],
                },
            },
            {
                "quantity": 2,
                "data": {
                    "name": "Forest",
                    "type_line": "Basic Land — Forest",
                    "cmc": 0.0,
                    "price_eur": 0.0,
                    "image_paths": [],
                    "faces": [{"name": "Forest", "mana_cost": "", "type_line": "", "rules_text": ""}],
                },
            },
        ],
    )

    body = client.get(f"/decks/{deck.id}").content.decode()
    # The button and its Moxfield-format payload (one "qty name" per line) are present.
    assert 'id="copy-decklist"' in body
    assert "Copy plain text" in body
    assert '<script id="decklist-plain"' in body
    assert "4 Llanowar Elves" in body
    assert "2 Forest" in body


@pytest.mark.django_db
def test_destructive_actions_use_confirm_modal(client):
    from mtg_deck_analyzer.models import Deck

    deck = Deck.objects.create(
        name="Confirm Me",
        raw_decklist="1 Forest",
        status=Deck.Status.READY,
        total_cards=1,
        total_value_eur=0.0,
        avg_cmc=0.0,
        category_counts={"Land": 1},
        cards=[],
    )

    # The deck list no longer carries a delete control; deletion lives on the
    # deck detail view.
    index = client.get("/").content.decode()
    assert "onsubmit=\"return confirm(" not in index
    assert f'action="/decks/{deck.id}/delete"' not in index

    # The deck detail re-run and delete actions are guarded by confirm modals.
    detail = client.get(f"/decks/{deck.id}").content.decode()
    assert "onsubmit=\"return confirm(" not in detail
    assert 'id="confirm-reanalyze"' in detail
    assert f'action="/decks/{deck.id}/reanalyze"' in detail
    assert 'id="confirm-delete"' in detail
    assert f'action="/decks/{deck.id}/delete"' in detail
