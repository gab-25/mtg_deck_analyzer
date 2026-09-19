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


def _seed_jpeg(name, rgb=(10, 120, 60)):
    """Stores a real opaque JPEG in the image cache so ReportLab can rasterize it."""
    import io

    from PIL import Image

    from mtg_deck_analyzer.models import ScryfallImage

    buf = io.BytesIO()
    Image.new("RGB", (63, 88), rgb).save(buf, format="JPEG")
    ScryfallImage.objects.create(name=name, data=buf.getvalue())
    return name


def _proxy_card(name, paths, quantity=1, type_line="Creature — Human Wizard"):
    return {
        "quantity": quantity,
        "data": {
            "name": name,
            "type_line": type_line,
            "cmc": 1.0,
            "price_eur": 0.0,
            "image_paths": list(paths),
            "faces": [{"name": name, "mana_cost": "", "type_line": "", "rules_text": ""}],
        },
    }


def _proxy_pages(pdf_bytes):
    """Page count of a ReportLab PDF: one /Type /Page per page, plus the /Pages node."""
    return pdf_bytes.count(b"/Type /Page") - 1


@pytest.mark.django_db
def test_proxy_pdf_download(client):
    from mtg_deck_analyzer.models import Deck

    _seed_jpeg("img_bolt.jpg")
    _seed_jpeg("img_forest.jpg")

    deck = Deck.objects.create(
        name="Mono Green",
        raw_decklist="3 Lightning Bolt\n3 Forest",
        status=Deck.Status.READY,
        total_cards=6,
        total_value_eur=0.0,
        avg_cmc=0.0,
        category_counts={"Instant": 3, "Land": 3},
        cards=[
            _proxy_card("Lightning Bolt", ["img_bolt.jpg"], quantity=3, type_line="Instant"),
            _proxy_card("Forest", ["img_forest.jpg"], quantity=3, type_line="Basic Land — Forest"),
        ],
    )

    pdf = client.get(f"/decks/{deck.id}/proxy")
    assert pdf.status_code == 200
    assert pdf["content-type"] == "application/pdf"
    body = b"".join(pdf.streaming_content)
    assert body.startswith(b"%PDF")
    # The deck must reach the page as real images. Asserting only on the %PDF
    # header passes just as happily on a sheet with nothing placed on it.
    assert b"/Image" in body


@pytest.mark.django_db
def test_proxy_pdf_prints_the_back_face_of_a_double_faced_card(client):
    from mtg_deck_analyzer.models import Deck

    _seed_jpeg("img_bolt.jpg")
    _seed_jpeg("img_delver_face0.jpg", rgb=(120, 20, 20))
    _seed_jpeg("img_delver_face1.jpg", rgb=(20, 20, 120))

    deck = Deck.objects.create(
        name="Delver Proxies",
        raw_decklist="8 Lightning Bolt\n1 Delver of Secrets",
        status=Deck.Status.READY,
        total_cards=9,
        total_value_eur=0.0,
        avg_cmc=1.0,
        category_counts={"Instant": 8, "Creature": 1},
        cards=[
            _proxy_card("Lightning Bolt", ["img_bolt.jpg"], quantity=8, type_line="Instant"),
            _proxy_card("Delver of Secrets", ["img_delver_face0.jpg", "img_delver_face1.jpg"]),
        ],
    )

    body = b"".join(client.get(f"/decks/{deck.id}/proxy").streaming_content)
    # 8 single-faced copies + a double-faced one = 10 slots at 9 per page, so two
    # pages. Printing the front only would be 9 slots and a single page: this is
    # what makes the back face's slot observable end to end.
    assert _proxy_pages(body) == 2


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
    # A single-faced card has nothing to flip to.
    assert "card-face-flip" not in body

    # No name -> empty body, which clears the container (closes the modal).
    close = client.get("/card-image")
    assert close.status_code == 200
    assert close.content.decode().strip() == ""


@pytest.mark.django_db
def test_card_image_modal_offers_a_flip_for_a_double_faced_card(client):
    from mtg_deck_analyzer.models import ScryfallImage

    ScryfallImage.objects.create(name="img_front.jpg", data=b"\x01")
    ScryfallImage.objects.create(name="img_back.jpg", data=b"\x02")

    r = client.get("/card-image", {"name": ["img_front.jpg", "img_back.jpg"]})
    assert r.status_code == 200
    body = r.content.decode()
    # Both faces ship in the fragment, so flipping costs no further request.
    assert 'src="/media/img_front.jpg"' in body
    assert 'src="/media/img_back.jpg"' in body
    # The flip is a label driving a hidden checkbox: CSS only, still no inline JS.
    assert 'for="card-face-flip"' in body
    assert "<script" not in body
    assert "onclick" not in body
    # Clicks bubble, so the backdrop's close trigger must be filtered to the
    # backdrop itself — otherwise clicking Flip would close the modal instead.
    assert 'hx-trigger="click target:#card-image-modal"' in body

    # A face that isn't cached still 404s, so the modal never opens half-empty.
    assert client.get(
        "/card-image", {"name": ["img_front.jpg", "img_gone.jpg"]}
    ).status_code == 404


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
def test_deck_detail_modal_link_carries_every_face(client):
    from mtg_deck_analyzer.models import Deck

    deck = Deck.objects.create(
        name="Delver Deck",
        raw_decklist="1 Delver of Secrets",
        status=Deck.Status.READY,
        total_cards=1,
        total_value_eur=0.0,
        avg_cmc=1.0,
        category_counts={"Creature": 1},
        cards=[
            {
                "quantity": 1,
                "data": {
                    "name": "Delver of Secrets",
                    "type_line": "Creature — Human Wizard",
                    "cmc": 1.0,
                    "price_eur": 0.0,
                    "image_paths": ["img_delver_face0.jpg", "img_delver_face1.jpg"],
                    "faces": [
                        {"name": "Delver of Secrets", "mana_cost": "{U}", "type_line": "", "rules_text": ""},
                        {"name": "Insectile Aberration", "mana_cost": "", "type_line": "", "rules_text": ""},
                    ],
                },
            }
        ],
    )

    body = client.get(f"/decks/{deck.id}").content.decode()
    # Both faces travel in the query string (`&` escaped, as it must be in HTML).
    assert (
        'hx-get="/card-image?name=img_delver_face0.jpg&amp;name=img_delver_face1.jpg"'
        in body
    )
    # The row thumbnail itself still shows the front face only.
    assert 'src="/media/img_delver_face0.jpg"' in body
    assert 'src="/media/img_delver_face1.jpg"' not in body


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


# --- Ownership and visibility -------------------------------------------------


@pytest.fixture
def owner(django_user_model):
    return django_user_model.objects.create_user(username="owner", password="pw")


def _owned_deck(owner, visibility="private", name="Owned"):
    """A ready deck belonging to ``owner``, straight into the database."""
    from mtg_deck_analyzer.models import Deck

    return Deck.objects.create(
        name=name,
        raw_decklist="1 Forest",
        owner=owner,
        visibility=visibility,
        status=Deck.Status.READY,
        total_cards=1,
        category_counts={"Land": 1},
        cards=[],
    )


@pytest.mark.django_db
def test_created_deck_belongs_to_the_submitting_user(client, django_user_model):
    from mtg_deck_analyzer.models import Deck

    client.post("/decks", data={"name": "Mine", "decklist": _legal_decklist()})
    deck = Deck.objects.get(name="Mine")
    assert deck.owner == django_user_model.objects.get(username="tester")
    # Private unless the submitter says otherwise.
    assert deck.visibility == Deck.Visibility.PRIVATE


@pytest.mark.django_db
def test_created_deck_honours_the_chosen_visibility(client):
    from mtg_deck_analyzer.models import Deck

    client.post(
        "/decks",
        data={
            "name": "Shared",
            "decklist": _legal_decklist(),
            "visibility": "unlisted",
        },
    )
    assert Deck.objects.get(name="Shared").visibility == Deck.Visibility.UNLISTED


@pytest.mark.django_db
def test_index_lists_only_your_own_decks_and_legacy_ones(client, owner):
    from mtg_deck_analyzer.models import Deck

    _owned_deck(owner, name="Someone Elses")
    Deck.objects.create(name="Legacy Pile", raw_decklist="1 Forest")
    client.post("/decks", data={"name": "My Deck", "decklist": _legal_decklist()})

    body = client.get("/").content.decode()
    assert "My Deck" in body
    # The ownerless deck predates ownership and stays visible to everyone.
    assert "Legacy Pile" in body
    assert "Someone Elses" not in body


@pytest.mark.django_db
def test_a_private_deck_is_404_for_another_user(client, owner):
    deck = _owned_deck(owner)
    # A 404 rather than a 403: another user's private deck does not exist for you.
    assert client.get(f"/decks/{deck.id}").status_code == 404
    assert client.get(f"/decks/{deck.id}/pdf").status_code == 404
    assert client.get(f"/decks/{deck.id}/proxy").status_code == 404
    assert client.get(f"/decks/{deck.id}/edit").status_code == 404
    assert client.post(f"/decks/{deck.id}/delete").status_code == 404
    assert client.post(f"/decks/{deck.id}/reanalyze").status_code == 404
    assert client.post(
        f"/decks/{deck.id}/update", data={"name": "Hijacked", "decklist": "1 Forest"}
    ).status_code == 404


@pytest.mark.django_db
def test_a_private_deck_sends_an_anonymous_visitor_to_the_login(client, owner):
    deck = _owned_deck(owner)
    client.logout()
    r = client.get(f"/decks/{deck.id}")
    assert r.status_code == 302
    assert r["Location"].startswith("/login")


@pytest.mark.django_db
def test_an_unlisted_deck_opens_for_anyone_holding_the_link(client, owner):
    deck = _owned_deck(owner, visibility="unlisted", name="Open Deck")

    # Another signed-in user.
    assert client.get(f"/decks/{deck.id}").status_code == 200
    # And an anonymous visitor.
    client.logout()
    r = client.get(f"/decks/{deck.id}")
    assert r.status_code == 200
    assert "Open Deck" in r.content.decode()


@pytest.mark.django_db
def test_an_unlisted_deck_is_still_not_editable_by_its_readers(client, owner):
    deck = _owned_deck(owner, visibility="unlisted")

    assert client.get(f"/decks/{deck.id}/edit").status_code == 404
    assert client.post(f"/decks/{deck.id}/delete").status_code == 404
    # And the page it can read offers it no destructive control.
    body = client.get(f"/decks/{deck.id}").content.decode()
    assert f'action="/decks/{deck.id}/delete"' not in body
    assert f'href="/decks/{deck.id}/edit"' not in body


@pytest.mark.django_db
def test_the_owner_still_sees_every_control(client, django_user_model):
    from mtg_deck_analyzer.models import Deck

    client.post("/decks", data={"name": "Mine", "decklist": _legal_decklist()})
    deck = Deck.objects.get(name="Mine")
    body = client.get(f"/decks/{deck.id}").content.decode()
    assert f'href="/decks/{deck.id}/edit"' in body
    assert f'action="/decks/{deck.id}/delete"' in body
    assert f'action="/decks/{deck.id}/reanalyze"' in body


@pytest.mark.django_db
def test_an_unlisted_deck_is_labelled_as_shared_for_its_owner(client):
    from mtg_deck_analyzer.models import Deck

    client.post(
        "/decks",
        data={"name": "Shared", "decklist": _legal_decklist(), "visibility": "unlisted"},
    )
    deck = Deck.objects.get(name="Shared")
    assert "Unlisted" in client.get(f"/decks/{deck.id}").content.decode()


@pytest.mark.django_db
def test_update_can_change_the_visibility(client):
    from mtg_deck_analyzer.models import Deck

    client.post("/decks", data={"name": "Mine", "decklist": _legal_decklist()})
    deck = Deck.objects.get(name="Mine")
    client.post(
        f"/decks/{deck.id}/update",
        data={
            "name": "Mine",
            "decklist": deck.raw_decklist,
            "visibility": "unlisted",
        },
    )
    deck.refresh_from_db()
    assert deck.visibility == Deck.Visibility.UNLISTED


@pytest.mark.django_db
def test_update_without_a_visibility_field_preserves_it(client, django_user_model):
    from mtg_deck_analyzer.models import Deck

    client.post(
        "/decks",
        data={"name": "Mine", "decklist": _legal_decklist(), "visibility": "unlisted"},
    )
    deck = Deck.objects.get(name="Mine")
    assert deck.visibility == Deck.Visibility.UNLISTED

    # A partial submission (name + decklist only, no visibility key at all)
    # must not silently un-share the deck.
    client.post(
        f"/decks/{deck.id}/update",
        data={"name": "Mine", "decklist": deck.raw_decklist},
    )
    deck.refresh_from_db()
    assert deck.visibility == Deck.Visibility.UNLISTED


@pytest.mark.django_db
def test_update_with_an_unrecognized_visibility_falls_back_to_private(client):
    from mtg_deck_analyzer.models import Deck

    client.post(
        "/decks",
        data={"name": "Mine", "decklist": _legal_decklist(), "visibility": "unlisted"},
    )
    deck = Deck.objects.get(name="Mine")

    # The field is present but holds a value the form never offers.
    client.post(
        f"/decks/{deck.id}/update",
        data={
            "name": "Mine",
            "decklist": deck.raw_decklist,
            "visibility": "public",
        },
    )
    deck.refresh_from_db()
    assert deck.visibility == Deck.Visibility.PRIVATE


@pytest.mark.django_db
def test_card_images_load_for_an_anonymous_reader_of_an_unlisted_deck(client, owner):
    from mtg_deck_analyzer.models import ScryfallImage

    _owned_deck(owner, visibility="unlisted")
    ScryfallImage.objects.create(name="img_seed.jpg", data=b"\x01")
    client.logout()

    # The card art cache is shared, public Scryfall data — without it an
    # unlisted page would render nothing but broken images.
    assert client.get("/media/img_seed.jpg").status_code == 200
    assert client.get("/card-image", {"name": "img_seed.jpg"}).status_code == 200


@pytest.mark.django_db
def test_legacy_ownerless_decks_stay_reachable_and_editable(client):
    from mtg_deck_analyzer.models import Deck

    deck = Deck.objects.create(
        name="Legacy",
        raw_decklist="1 Forest",
        status=Deck.Status.READY,
        total_cards=1,
        category_counts={"Land": 1},
        cards=[],
    )
    assert client.get(f"/decks/{deck.id}").status_code == 200
    assert client.get(f"/decks/{deck.id}/edit").status_code == 200


# --- FAILED-deck controls are also owner-gated -------------------------------


@pytest.mark.django_db
def test_a_failed_unlisted_deck_hides_owner_controls_from_a_reader(client, owner):
    from mtg_deck_analyzer.models import Deck

    deck = Deck.objects.create(
        name="Broke",
        raw_decklist="1 Forest",
        owner=owner,
        visibility=Deck.Visibility.UNLISTED,
        status=Deck.Status.FAILED,
        error="Not a valid decklist.",
    )
    client.logout()
    r = client.get(f"/decks/{deck.id}")
    assert r.status_code == 200
    body = r.content.decode()
    assert f'href="/decks/{deck.id}/edit"' not in body
    assert f'action="/decks/{deck.id}/delete"' not in body
    assert f'action="/decks/{deck.id}/reanalyze"' not in body


@pytest.mark.django_db
def test_a_failed_deck_shows_every_control_to_its_owner(client, django_user_model):
    from mtg_deck_analyzer.models import Deck

    tester = django_user_model.objects.get(username="tester")
    deck = Deck.objects.create(
        name="Broke",
        raw_decklist="1 Forest",
        owner=tester,
        status=Deck.Status.FAILED,
        error="Not a valid decklist.",
    )
    body = client.get(f"/decks/{deck.id}").content.decode()
    assert f'href="/decks/{deck.id}/edit"' in body
    assert f'action="/decks/{deck.id}/delete"' in body
    assert f'action="/decks/{deck.id}/reanalyze"' in body


# --- Version history ----------------------------------------------------------


@pytest.mark.django_db
def test_creating_a_deck_records_its_first_version(client):
    from mtg_deck_analyzer.models import Deck

    client.post("/decks", data={"name": "Mine", "decklist": _legal_decklist()})
    deck = Deck.objects.get(name="Mine")

    versions = list(deck.versions.all())
    assert len(versions) == 1
    assert versions[0].raw_decklist == _legal_decklist()


@pytest.mark.django_db
def test_every_decklist_change_appends_a_version(client):
    from mtg_deck_analyzer.models import Deck

    client.post("/decks", data={"name": "Mine", "decklist": _legal_decklist()})
    deck = Deck.objects.get(name="Mine")
    second = _legal_decklist().replace("1 Spell 0", "1 Rhystic Study")

    client.post(
        f"/decks/{deck.id}/update",
        data={"name": "Mine", "decklist": second, "note": "Added the tax"},
    )

    versions = list(deck.versions.all())
    # Oldest first: the trail is append-only, nothing is rewritten.
    assert len(versions) == 2
    assert versions[0].raw_decklist == _legal_decklist()
    assert versions[1].raw_decklist == second
    assert versions[1].note == "Added the tax"


@pytest.mark.django_db
def test_a_plain_rename_does_not_append_a_version(client):
    from mtg_deck_analyzer.models import Deck

    client.post("/decks", data={"name": "Mine", "decklist": _legal_decklist()})
    deck = Deck.objects.get(name="Mine")

    client.post(
        f"/decks/{deck.id}/update",
        data={"name": "Renamed", "decklist": _legal_decklist()},
    )

    # The card list is what a version records; a title change is not one.
    assert deck.versions.count() == 1


@pytest.mark.django_db
def test_a_rejected_update_records_nothing(client):
    from mtg_deck_analyzer.models import Deck

    client.post("/decks", data={"name": "Mine", "decklist": _legal_decklist()})
    deck = Deck.objects.get(name="Mine")

    r = client.post(
        f"/decks/{deck.id}/update", data={"name": "Mine", "decklist": "1 Sol Ring"}
    )
    assert r.status_code == 422
    # Only a successful update is part of the history.
    assert deck.versions.count() == 1


@pytest.mark.django_db
def test_deleting_a_deck_takes_its_versions_with_it(client):
    from mtg_deck_analyzer.models import Deck, DeckVersion

    client.post("/decks", data={"name": "Mine", "decklist": _legal_decklist()})
    deck = Deck.objects.get(name="Mine")
    client.post(f"/decks/{deck.id}/delete")

    assert not DeckVersion.objects.filter(deck_id=deck.id).exists()


def _revise(client, deck, decklist, note=""):
    """Posts a new card list for ``deck`` and returns the version it created."""
    client.post(
        f"/decks/{deck.id}/update",
        data={"name": deck.name, "decklist": decklist, "note": note},
    )
    return deck.versions.last()


@pytest.mark.django_db
def test_deck_page_lists_the_versions_with_their_changelog(client):
    from mtg_deck_analyzer.models import Deck

    client.post("/decks", data={"name": "Mine", "decklist": _legal_decklist()})
    deck = Deck.objects.get(name="Mine")
    second = _legal_decklist().replace("1 Spell 0", "1 Rhystic Study")
    _revise(client, deck, second, note="Added the tax")

    body = client.get(f"/decks/{deck.id}").content.decode()
    assert "Version history" in body
    # The changelog against the version before, in the +/- form.
    assert "+1 Rhystic Study" in body
    assert "-1 Spell 0" in body
    assert "Added the tax" in body
    # The oldest version has nothing to compare against.
    assert "Initial version" in body


@pytest.mark.django_db
def test_an_older_version_can_be_opened(client):
    from mtg_deck_analyzer.models import Deck

    client.post("/decks", data={"name": "Mine", "decklist": _legal_decklist()})
    deck = Deck.objects.get(name="Mine")
    first = deck.versions.first()
    _revise(client, deck, _legal_decklist().replace("1 Spell 0", "1 Rhystic Study"))

    r = client.get(f"/decks/{deck.id}/versions/{first.id}")
    assert r.status_code == 200
    body = r.content.decode()
    # The stored list as it was, in full.
    assert "1 Spell 0" in body
    assert "Rhystic Study" not in body


@pytest.mark.django_db
def test_a_version_cannot_be_read_across_decks(client):
    from mtg_deck_analyzer.models import Deck

    client.post("/decks", data={"name": "One", "decklist": _legal_decklist()})
    client.post("/decks", data={"name": "Two", "decklist": _legal_decklist()})
    one = Deck.objects.get(name="One")
    two = Deck.objects.get(name="Two")

    # A version id belonging to another deck is not reachable through this one.
    assert client.get(f"/decks/{one.id}/versions/{two.versions.first().id}").status_code == 404


@pytest.mark.django_db
def test_version_pages_follow_the_same_access_rule_as_the_deck(client, owner):
    from mtg_deck_analyzer.models import Deck, DeckVersion

    deck = _owned_deck(owner)
    version = DeckVersion.objects.create(deck=deck, raw_decklist="1 Forest")

    # Another user: the deck is private, so its history is too.
    assert client.get(f"/decks/{deck.id}/versions/{version.id}").status_code == 404

    deck.visibility = Deck.Visibility.UNLISTED
    deck.save(update_fields=["visibility"])
    assert client.get(f"/decks/{deck.id}/versions/{version.id}").status_code == 200


@pytest.mark.django_db
def test_a_deck_without_versions_shows_no_history_panel(client):
    from mtg_deck_analyzer.models import Deck

    # A legacy deck, created before versions existed.
    deck = Deck.objects.create(
        name="Legacy",
        raw_decklist="1 Forest",
        status=Deck.Status.READY,
        total_cards=1,
        category_counts={"Land": 1},
        cards=[],
    )
    assert "Version history" not in client.get(f"/decks/{deck.id}").content.decode()
@pytest.mark.django_db
def test_a_new_deck_defaults_to_the_commander_format():
    from mtg_deck_analyzer.models import Deck

    deck = Deck.objects.create(name="Untitled", raw_decklist="")
    assert deck.format == "commander"


@pytest.mark.django_db
def test_the_format_is_persisted():
    from mtg_deck_analyzer.models import Deck

    deck = Deck.objects.create(name="Duel", raw_decklist="", format="duel")
    assert Deck.objects.get(pk=deck.pk).format == "duel"


@pytest.mark.django_db
def test_creating_a_deck_persists_the_chosen_format(client):
    from mtg_deck_analyzer.models import Deck

    r = client.post(
        "/decks",
        data={"name": "Duel Deck", "decklist": _legal_decklist(), "format": "duel"},
    )
    assert r.status_code == 302
    assert Deck.objects.get(name="Duel Deck").format == "duel"


@pytest.mark.django_db
def test_creating_a_deck_without_a_format_defaults_to_commander(client):
    from mtg_deck_analyzer.models import Deck

    client.post("/decks", data={"name": "Plain", "decklist": _legal_decklist()})
    assert Deck.objects.get(name="Plain").format == "commander"


@pytest.mark.django_db
def test_an_unknown_format_falls_back_to_the_default(client):
    # Only a tampered or stale form can send this; it must not be a 500.
    from mtg_deck_analyzer.models import Deck

    r = client.post(
        "/decks",
        data={"name": "Tampered", "decklist": _legal_decklist(), "format": "nonsense"},
    )
    assert r.status_code == 302
    assert Deck.objects.get(name="Tampered").format == "commander"


@pytest.mark.django_db
def test_changing_only_the_format_triggers_a_reanalysis(client, monkeypatch):
    from mtg_deck_analyzer import views
    from mtg_deck_analyzer.models import Deck

    client.post("/decks", data={"name": "Deck", "decklist": _legal_decklist()})
    deck = Deck.objects.get(name="Deck")
    assert deck.status == Deck.Status.READY

    started = []
    monkeypatch.setattr(views, "_start_analysis", lambda *a: started.append(a))

    r = client.post(
        f"/decks/{deck.id}/update",
        data={"name": "Deck", "decklist": deck.raw_decklist, "format": "duel"},
    )
    assert r.status_code == 302

    deck.refresh_from_db()
    assert deck.format == "duel"
    assert deck.status == Deck.Status.PENDING
    assert started, "changing the format must re-run the analysis"


@pytest.mark.django_db
def test_renaming_alone_does_not_trigger_a_reanalysis(client, monkeypatch):
    from mtg_deck_analyzer import views
    from mtg_deck_analyzer.models import Deck

    client.post("/decks", data={"name": "Deck", "decklist": _legal_decklist()})
    deck = Deck.objects.get(name="Deck")

    started = []
    monkeypatch.setattr(views, "_start_analysis", lambda *a: started.append(a))

    client.post(
        f"/decks/{deck.id}/update",
        data={
            "name": "Renamed",
            "decklist": deck.raw_decklist,
            "format": deck.format,
        },
    )

    deck.refresh_from_db()
    assert deck.name == "Renamed"
    assert deck.status == Deck.Status.READY
    assert not started, "a plain rename must not re-run minutes of work"


@pytest.mark.django_db
def test_reanalyzing_keeps_the_stored_format(client, monkeypatch):
    from mtg_deck_analyzer import views
    from mtg_deck_analyzer.models import Deck

    client.post(
        "/decks",
        data={"name": "Deck", "decklist": _legal_decklist(), "format": "duel"},
    )
    deck = Deck.objects.get(name="Deck")

    started = []
    monkeypatch.setattr(views, "_start_analysis", lambda *a: started.append(a))
    client.post(f"/decks/{deck.id}/reanalyze")

    assert started and started[0][3] == "duel"


@pytest.mark.django_db
def test_the_create_form_offers_both_formats(client):
    body = client.get("/decks/new").content.decode()
    assert 'name="format"' in body
    assert "Duel Commander" in body


@pytest.mark.django_db
def test_the_edit_form_preselects_the_decks_format(client):
    from mtg_deck_analyzer.models import Deck

    client.post(
        "/decks",
        data={"name": "Duel Deck", "decklist": _legal_decklist(), "format": "duel"},
    )
    deck = Deck.objects.get(name="Duel Deck")

    body = client.get(f"/decks/{deck.id}/edit").content.decode()
    assert '<option value="duel" selected>' in body


@pytest.mark.django_db
def test_the_deck_page_shows_the_format_badge(client):
    from mtg_deck_analyzer.models import Deck

    client.post(
        "/decks",
        data={"name": "Duel Deck", "decklist": _legal_decklist(), "format": "duel"},
    )
    deck = Deck.objects.get(name="Duel Deck")

    body = client.get(f"/decks/{deck.id}").content.decode()
    assert "Duel Commander" in body
