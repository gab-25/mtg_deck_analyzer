"""Django views: server-rendered (Tailwind) front-end for the deck analyzer."""

import logging
import os
import tempfile
import threading
import uuid

import markdown as md
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .access import can_edit, decks_visible_in_library, requires_deck_edit, requires_deck_view
from .caching.db_cache import DbCardCache
from .domain.cards import classify_card
from .domain.changelog import decklist_changes
from .domain.commander import check_decklist, commanders, deck_color_identity
from .domain.constants import CATEGORY_ORDER, COLOR_FULL_NAMES, DEFAULT_FORMAT
from .domain.constants import FORMATS, format_choices
from .domain.decklist import parse_decklist_text
from .domain.statistics import STATISTICS_SCHEMA, curve_bars
from .domain.storage import (
    cards_for_pdf,
    cards_for_storage,
    image_query,
    image_urls,
    proxy_images,
)
from .domain.text_utils import slugify
from .logging_context import deck_log_context
from .models import Deck, DeckVersion
from .pipeline import analyze_decklist
from .rendering.pdf import generate_pdf, generate_proxy_pdf

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


def _deck_pips(deck) -> list:
    """Color pips for a deck: the commander's color identity, in WUBRG order.

    Uses the identity stored at analysis time, deriving it from the deck's cards
    for decks analyzed before it was persisted. Falls back to a single colorless
    pip for a lands-only / artifact deck.
    """
    letters = deck.color_identity or deck_color_identity(deck.cards or []) or ["C"]
    return [{"letter": c, "hex": COLOR_HEX.get(c, COLOR_HEX["C"])} for c in letters]


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


def _pct(probability: float) -> int:
    """A probability as a whole percentage, which is all the panel shows."""
    return round(probability * 100)


# The land counts a hand is kept on without thinking about it. Bars outside
# this window are the ones a mulligan decision turns on, so the chart marks it.
_KEEPABLE_WINDOW = range(2, 6)


def _land_distribution(land_counts: list) -> dict:
    """Geometry for the opening-hand distribution, drawn like the sparklines.

    Every land count from none to seven, so the unkeepable tail is visible
    rather than cropped away — showing only the window states the conclusion
    and hides the evidence for it.
    """
    peak = max((entry["p"] for entry in land_counts), default=0) or 1
    width, height, gap = 240, 46, 4.0
    slot = width / len(land_counts)
    return {
        "width": width,
        "height": height,
        "bars": [
            {
                "lands": entry["lands"],
                "pct": _pct(entry["p"]),
                "keepable": entry["lands"] in _KEEPABLE_WINDOW,
                "x": round(slot * index, 2),
                "width": round(slot - gap, 2),
                "label_x": round(slot * index + (slot - gap) / 2, 2),
                "y": round(height * (1 - entry["p"] / peak), 2),
                "height": round(height * entry["p"] / peak, 2),
            }
            for index, entry in enumerate(land_counts)
        ],
    }


def _opening_hand_rows(opening_hand: dict) -> dict:
    """The opening-hand block with every probability turned into a percentage."""
    keepable = opening_hand["keepable"]
    return {
        "hand_size": opening_hand["hand_size"],
        "keepable": _pct(keepable),
        "average_lands": f"{opening_hand['average_lands']:.2f}",
        # "One hand in six" reads as a decision; "16%" reads as a statistic.
        "mulligan_in": round(1 / (1 - keepable)) if keepable < 1 else 0,
        "distribution": _land_distribution(opening_hand["land_counts"]),
        "land_drops": [
            {"turn": entry["turn"], "pct": _pct(entry["p"])}
            for entry in opening_hand["land_drops"]
        ],
    }


# Chart box in SVG user units. The viewBox scales to whatever width the panel
# gives it, so these are proportions rather than pixels.
# "top" leaves room for the y-axis caption above the highest gridline, and
# "bottom" for the bucket labels and the x-axis caption below the baseline.
# Too little of either and a caption prints over a tick.
_CHART = {"w": 560, "h": 252, "left": 38, "bottom": 34, "top": 28}
_CAPTION_Y = 10


def _y_ticks(peak: int) -> list:
    """Round tick values covering 0..peak, at a step that stays readable."""
    step = 10 if peak > 20 else (5 if peak > 5 else 1)
    top = max(step, -(-peak // step) * step)
    return list(range(0, top + step, step))


def _curve_chart(curve: list) -> dict:
    """Ready-to-draw geometry for the stacked curve.

    Computed here because a Django template cannot do arithmetic, and drawn as
    SVG because the project's stylesheet is a committed Tailwind build with no
    build step — a class it does not already carry silently does nothing.
    """
    bars = curve_bars(curve)
    ticks = _y_ticks(max((b["total"] for b in bars), default=0))
    top_value = ticks[-1]

    plot_h = _CHART["h"] - _CHART["bottom"] - _CHART["top"]
    plot_w = _CHART["w"] - _CHART["left"]
    slot = plot_w / len(bars)
    bar_w = slot * 0.62

    def y_of(value: float) -> float:
        return _CHART["top"] + plot_h * (1 - value / top_value)

    out = []
    for index, bar in enumerate(bars):
        x = _CHART["left"] + slot * index + (slot - bar_w) / 2
        perm_h = plot_h * bar["permanents"] / top_value
        spell_h = plot_h * bar["spells"] / top_value
        out.append({
            "label": bar["label"],
            "total": bar["total"],
            "x": round(x, 2),
            "width": round(bar_w, 2),
            "label_x": round(x + bar_w / 2, 2),
            # Permanents sit on the axis, spells stack on top of them.
            "permanents": {"y": round(y_of(bar["permanents"]), 2),
                           "height": round(perm_h, 2)},
            "spells": {"y": round(y_of(bar["total"]), 2),
                       "height": round(spell_h, 2)},
        })

    return {
        "width": _CHART["w"], "height": _CHART["h"],
        "caption_y": _CAPTION_Y,
        # Clear of the bucket labels, and inside the box so nothing is clipped.
        "x_label_y": _CHART["h"] - 2,
        "axis_x": _CHART["left"],
        "label_y": round(y_of(0) + 16, 2),
        "bars": out,
        "gridlines": [{"value": t, "y": round(y_of(t), 2)} for t in ticks],
    }


def _sparkline(values: list) -> dict:
    """A small bar chart for one colour's curve, same idea as _curve_chart."""
    peak = max(values, default=0) or 1
    width, height, gap = 56, 18, 1.0
    slot = width / len(values)
    return {
        "width": width, "height": height,
        "bars": [
            {"x": round(slot * i, 2), "width": round(slot - gap, 2),
             "y": round(height * (1 - v / peak), 2),
             "height": round(height * v / peak, 2)}
            for i, v in enumerate(values)
        ],
    }


def _stored_statistics(deck) -> dict | None:
    """The deck's stored statistics, or None when they predate the current shape.

    Both routes into the panel need this: a blob from before the schema existed
    is not empty, it simply has different keys, so an emptiness check lets it
    through into code that will raise on the first missing one.
    """
    stored = deck.statistics or {}
    return stored if stored.get("schema") == STATISTICS_SCHEMA else None


def _statistics_panel(deck) -> dict | None:
    """View-model for the Statistics panel, or None when there is nothing yet.

    The statistics are computed when the deck is analyzed and never here: a
    deck whose blob predates the current shape has no panel until the backfill
    command or a re-analysis replaces it.
    """
    stored = _stored_statistics(deck)
    if stored is None or not stored.get("library_size"):
        return None

    mv = stored["mana_values"]
    return {
        "library_size": stored["library_size"],
        "land_count": stored["land_count"],
        "sources_known": stored["sources_known"],
        "curve_chart": _curve_chart(stored["curve"]),
        "mana_values": {
            "total": mv["total"],
            "average": f"{mv['average']:.2f}",
            "average_without_lands": f"{mv['average_without_lands']:.2f}",
            "median": f"{mv['median']:g}",
            "median_without_lands": f"{mv['median_without_lands']:g}",
        },
        "colors": [
            {**{k: v for k, v in entry.items() if k != "curve"},
             "name": COLOR_FULL_NAMES[entry["key"]],
             "hex": COLOR_HEX[entry["key"]],
             "used": entry["card_pct"] > 0 or entry["symbol_pct"] > 0,
             "sparkline": _sparkline(entry["curve"])}
            for entry in stored["colors"]
        ],
        "opening_hand": _opening_hand_rows(stored["opening_hand"]),
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
                    # The row shows the front face; the modal carries them all.
                    "image": urls[0] if urls else "",
                    "image_query": image_query(data),
                    "is_commander": item.get("is_commander", False),
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


def _commander_cards(stored_cards: list) -> list:
    """View-models for the commander(s) featured at the top of the deck page."""
    cards = []
    for item in commanders(stored_cards):
        data = item["data"]
        urls = image_urls(data)
        cards.append(
            {
                "name": data.get("name", ""),
                "type_line": data.get("type_line", ""),
                "image": urls[0] if urls else "",
                "image_query": image_query(data),
            }
        )
    return cards


def _moxfield_text(stored_cards: list) -> str:
    """Renders the decklist as Moxfield-style plain text: one ``qty name`` per
    line, with the commander in its own section (the format it's parsed back in).
    """
    lines = []
    cmdrs = commanders(stored_cards)
    if cmdrs:
        lines.append("Commander")
        lines.extend(
            f"{item['quantity']} {item['data'].get('name', '')}" for item in cmdrs
        )
        lines.append("")
        lines.append("Deck")
    lines.extend(
        f"{item['quantity']} {item['data'].get('name', '')}"
        for item in stored_cards
        if not item.get("is_commander")
    )
    return "\n".join(lines)


def _version_entry(versions: list, position: int) -> dict:
    """Builds one version's view-model: its number, currency and changelog.

    ``versions`` is the deck's full history, oldest first (model ordering);
    ``position`` is this entry's index into it. Shared by ``_version_history``
    (every entry) and ``deck_version`` (a single one), so both compute the
    same numbering, "current" flag and diff-against-the-previous-version the
    same way.
    """
    version = versions[position]
    previous = versions[position - 1] if position else None
    return {
        "version": version,
        "number": position + 1,
        "is_current": position == len(versions) - 1,
        "changes": (
            decklist_changes(previous.raw_decklist, version.raw_decklist)
            if previous
            else []
        ),
    }


def _version_history(deck) -> list:
    """The deck's versions, newest first, each against the one before it.

    The trail is short by nature (one row per submitted list), so it is read
    whole and diffed in memory rather than paged. The oldest version has no
    predecessor and therefore no changelog.
    """
    versions = list(deck.versions.all())  # Oldest first (model ordering).
    return [
        _version_entry(versions, position)
        for position in range(len(versions) - 1, -1, -1)
    ]


def _resolved_api_key() -> str | None:
    return os.environ.get("OPENROUTER_API_KEY")


def _create_context(**extra) -> dict:
    """Builds the context the deck-creation form renders with."""
    return {"format_choices": format_choices(), "default_format": DEFAULT_FORMAT, **extra}


def _posted_format(request) -> str:
    """The format chosen in the form, falling back to the default.

    An unknown value can only come from a tampered or stale form, and is not
    worth a 500: the deck is simply treated as the format it would have been
    before the choice existed.
    """
    fmt = request.POST.get("format") or DEFAULT_FORMAT
    return fmt if fmt in FORMATS else DEFAULT_FORMAT


def _decklist_errors(decklist: str) -> list:
    """Validates a pasted decklist before any expensive work is started.

    Returns the reasons the deck cannot be accepted; an empty list means it
    passes every rule that plain text can settle. The rules that need the real
    cards (commander eligibility, color identity) are enforced afterwards by the
    pipeline, which fails the analysis rather than storing an illegal deck.
    """
    entries = parse_decklist_text(decklist)
    if not entries:
        return ["No cards could be parsed from the decklist."]
    return check_decklist(entries)


def _visibility(post, current: str | None = None) -> str:
    """Reads the visibility choice off a submitted form.

    A form that omits the field entirely leaves the deck's current visibility
    alone — a partial submission must never silently un-share a deck. A value
    that is present but unrecognized falls back to private, so a malformed
    form never shares one by accident.
    """
    if "visibility" not in post:
        return current or Deck.Visibility.PRIVATE
    value = post.get("visibility")
    allowed = {choice for choice, _ in Deck.Visibility.choices}
    return value if value in allowed else Deck.Visibility.PRIVATE


def _run_analysis(deck_id: uuid.UUID, decklist: str, api_key: str | None, fmt: str):
    """Runs the heavy analysis for ``deck_id`` and persists the outcome.

    Binds the deck id to the logging context so every record emitted during the
    run — including those from the pipeline/Scryfall/OpenRouter modules — is stamped
    with ``[deck <id>]``.
    """
    with deck_log_context(deck_id):
        try:
            Deck.objects.filter(pk=deck_id).update(status=Deck.Status.PROCESSING)
            result = analyze_decklist(
                decklist,
                api_key=api_key,
                cache=DbCardCache(),
                progress=lambda msg: logger.info("%s", msg),
                fmt=fmt,
            )
            stats = result["stats"]
            Deck.objects.filter(pk=deck_id).update(
                analysis_md=result["deck_analysis"],
                commanders=stats["commanders"],
                color_identity=stats["color_identity"],
                total_cards=stats["total_cards"],
                total_value_eur=stats["total_value_eur"],
                category_counts=stats["category_counts"],
                statistics=stats["statistics"],
                cards=cards_for_storage(result["processed_cards"]),
                status=Deck.Status.READY,
                error=None,
            )
            logger.info(
                "Deck analysis completed (%s cards, commander: %s)",
                stats["total_cards"],
                ", ".join(stats["commanders"]) or "none declared",
            )
        except Exception as exc:  # noqa: BLE001 - record any failure for the user.
            logger.exception("Deck analysis failed")
            Deck.objects.filter(pk=deck_id).update(
                status=Deck.Status.FAILED, error=str(exc)
            )


def _run_analysis_threaded(deck_id, decklist, api_key, fmt):
    """Thread entry point: runs the analysis, then releases the DB connection.

    The background thread gets its own connection from Django's thread-local
    pool; close it on the way out so it isn't left dangling.
    """
    try:
        _run_analysis(deck_id, decklist, api_key, fmt)
    finally:
        connection.close()


def _start_analysis(deck_id: uuid.UUID, decklist: str, api_key: str | None, fmt: str):
    """Kicks off the analysis, in a background thread unless disabled (tests)."""
    if getattr(settings, "ASYNC_DECK_ANALYSIS", True):
        threading.Thread(
            target=_run_analysis_threaded,
            args=(deck_id, decklist, api_key, fmt),
            daemon=True,
        ).start()
    else:
        _run_analysis(deck_id, decklist, api_key, fmt)


@login_required
@require_http_methods(["GET"])
def index(request):
    query = (request.GET.get("q") or "").strip()
    # The library is the signed-in user's own decks plus the ownerless ones that
    # predate ownership — those belonged to everybody and still do.
    owned = decks_visible_in_library(request.user)
    decks = list(owned.order_by("-created_at"))
    if query:
        needle = query.lower()
        decks = [d for d in decks if needle in d.name.lower()]

    # Annotate each deck with its color pips for the list cards.
    for deck in decks:
        deck.pips = _deck_pips(deck)

    # Whether any listed deck is still being analyzed; drives the HTMX polling.
    has_processing = any(
        d.status in {Deck.Status.PENDING, Deck.Status.PROCESSING} for d in decks
    )

    # Library-wide stats for the header cards (independent of the search filter).
    all_decks = owned
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
    return render(
        request, "create.html", _create_context(form_visibility=Deck.Visibility.PRIVATE)
    )


@login_required
@require_http_methods(["POST"])
def create_deck(request):
    name = (request.POST.get("name") or "").strip() or "Untitled Deck"
    decklist = request.POST.get("decklist", "")
    fmt = _posted_format(request)

    # Cheap, synchronous validation so an illegal deck is reported inline; the
    # multi-minute Scryfall + OpenRouter work happens in the background afterwards.
    errors = _decklist_errors(decklist)
    if errors:
        return render(
            request,
            "create.html",
            _create_context(
                errors=errors,
                form_name=name,
                form_decklist=decklist,
                form_visibility=_visibility(request.POST),
                form_format=fmt,
            ),
            status=422,
        )

    deck = Deck.objects.create(
        name=name,
        raw_decklist=decklist,
        status=Deck.Status.PENDING,
        owner=request.user,
        visibility=_visibility(request.POST),
        format=fmt,
    )
    # The list as submitted opens the deck's history.
    DeckVersion.objects.create(deck=deck, raw_decklist=decklist)
    _start_analysis(deck.id, decklist, _resolved_api_key(), fmt)

    # Post/Redirect/Get: back to the deck list, where the new deck shows an
    # "Analyzing…" status and the list polls itself until it's ready.
    return redirect("index")


@require_http_methods(["GET"])
@requires_deck_view
def deck_detail(request, deck):
    # While the analysis is still running there's nothing to show yet. A caller
    # who can reach the library (the owner, or anyone on an ownerless legacy
    # deck) goes there instead, where the deck shows its live "Analyzing…"
    # status. Everyone else — most notably an anonymous visitor holding an
    # unlisted link — can't reach `index` (it's login-gated), so sending them
    # there would just be a dead end through the login page; they get a small
    # standalone page instead.
    if deck.status in {Deck.Status.PENDING, Deck.Status.PROCESSING}:
        if can_edit(request.user, deck):
            return redirect("index")
        return render(request, "deck_analyzing.html", {"deck": deck})
    if deck.status == Deck.Status.FAILED:
        return render(
            request,
            "deck_failed.html",
            {
                "deck": deck,
                "can_edit": can_edit(request.user, deck),
                "version_history": _version_history(deck),
            },
        )

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
            "can_edit": can_edit(request.user, deck),
            "analysis_html": analysis_html,
            "pips": _deck_pips(deck),
            "commander_cards": _commander_cards(stored_cards),
            "card_groups": _detail_card_groups(stored_cards),
            "moxfield_text": _moxfield_text(stored_cards),
            "statistics": _statistics_panel(deck),
            "type_bars": _type_bars(deck.category_counts or {}),
            "value_stats": _value_stats(stored_cards, deck.total_value_eur),
            "version_history": _version_history(deck),
        },
    )


@require_http_methods(["GET"])
@requires_deck_view
def deck_version(request, deck, version_id: int):
    """Shows one stored decklist from the deck's history.

    Read-only by design: restoring a version re-opens the analysis lifecycle
    and is deliberately not part of this feature.
    """
    versions = list(deck.versions.all())
    position = next(
        (i for i, v in enumerate(versions) if v.id == version_id), None
    )
    if position is None:
        raise Http404("No version matches the given query.")

    entry = _version_entry(versions, position)
    return render(
        request,
        "deck_version.html",
        {
            "deck": deck,
            "version": entry["version"],
            "number": entry["number"],
            "is_current": entry["is_current"],
            "changes": entry["changes"],
        },
    )


@require_http_methods(["GET"])
@requires_deck_edit
def edit_deck(request, deck):
    return render(
        request,
        "edit.html",
        _create_context(
            deck=deck,
            form_name=deck.name,
            form_decklist=deck.raw_decklist,
            form_visibility=deck.visibility,
            form_note="",
            form_format=deck.format,
        ),
    )


@require_http_methods(["POST"])
@requires_deck_edit
def update_deck(request, deck):
    name = (request.POST.get("name") or "").strip() or "Untitled Deck"
    decklist = request.POST.get("decklist", "")
    visibility = _visibility(request.POST, current=deck.visibility)
    note = request.POST.get("note") or ""
    fmt = _posted_format(request)

    errors = _decklist_errors(decklist)
    if errors:
        return render(
            request,
            "edit.html",
            _create_context(
                deck=deck,
                errors=errors,
                form_name=name,
                form_decklist=decklist,
                form_visibility=visibility,
                form_note=note,
                form_format=fmt,
            ),
            status=422,
        )

    # The decklist and the format both feed the analysis — the format picks the
    # ban list the deck is validated against — so either one changing has to
    # re-run it. A plain rename still triggers nothing.
    decklist_changed = decklist != deck.raw_decklist
    needs_reanalysis = decklist_changed or fmt != deck.format

    deck.name = name
    deck.raw_decklist = decklist
    deck.visibility = visibility
    deck.format = fmt
    if needs_reanalysis:
        deck.status = Deck.Status.PENDING
        deck.error = None
    deck.save()

    # Only a real change to the card list is worth a version: a rename, or a
    # format switch that leaves the same 100 cards, would add a row whose
    # changelog is empty.
    if decklist_changed:
        DeckVersion.objects.create(
            deck=deck,
            raw_decklist=decklist,
            note=note.strip()[:255],
        )

    if needs_reanalysis:
        _start_analysis(deck.id, decklist, _resolved_api_key(), fmt)
        return redirect("index")
    return redirect("deck_detail", deck_id=deck.id)


@require_http_methods(["POST"])
@requires_deck_edit
def reanalyze_deck(request, deck):
    """Re-runs the analysis for an existing deck from its stored decklist."""
    deck.status = Deck.Status.PENDING
    deck.error = None
    deck.save(update_fields=["status", "error"])
    _start_analysis(deck.id, deck.raw_decklist, _resolved_api_key(), deck.format)

    # Back to the list, where the deck shows its live "Analyzing…" status and the
    # list polls itself until the re-analysis is done.
    return redirect("index")


@require_http_methods(["POST"])
@requires_deck_edit
def delete_deck(request, deck):
    deck.delete()
    return redirect("index")


@require_http_methods(["GET"])
@requires_deck_view
def deck_pdf(request, deck):
    # The PDF needs the fetched cards; they only exist once analysis is done.
    if deck.status != Deck.Status.READY:
        return redirect("deck_detail", deck_id=deck.id)

    processed = cards_for_pdf(deck.cards or [], DbCardCache())

    fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    generate_pdf(
        deck.name,
        deck.analysis_md,
        processed,
        tmp_path,
        commanders=deck.commanders,
        fmt=deck.format,
        statistics=_stored_statistics(deck),
    )

    filename = f"{slugify(deck.name) or 'deck'}.pdf"
    return FileResponse(
        open(tmp_path, "rb"),
        content_type="application/pdf",
        as_attachment=True,
        filename=filename,
    )


@require_http_methods(["GET"])
@requires_deck_view
def deck_proxy_pdf(request, deck):
    """Generates a 1:1 proxy PDF: every card image repeated by its quantity."""
    # The proxies need the fetched images; they only exist once analysis is done.
    if deck.status != Deck.Status.READY:
        return redirect("deck_detail", deck_id=deck.id)

    images = proxy_images(deck.cards or [], DbCardCache())

    fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    generate_proxy_pdf(deck.name, images, tmp_path)

    filename = f"{slugify(deck.name) or 'deck'}-proxies.pdf"
    return FileResponse(
        open(tmp_path, "rb"),
        content_type="application/pdf",
        as_attachment=True,
        filename=filename,
    )


# The card art cache is shared across every deck and keyed by card name: public
# Scryfall data, not user data. Serving it without a login is what lets an
# unlisted deck page actually render for the visitor holding its link.
@require_http_methods(["GET"])
def media(request, name: str):
    """Serves a cached card image from the database."""
    data = DbCardCache().get_image(name)
    if data is None:
        return HttpResponse("Image not found", status=404)
    return HttpResponse(data, content_type="image/jpeg")


@require_http_methods(["GET"])
def card_image_modal(request):
    """Returns the zoom-modal fragment for a cached card's faces (HTMX).

    The thumbnail buttons in the deck view ``hx-get`` this endpoint with one
    ``name`` per printed face, so a double-faced card ships both images in the
    same fragment and the flip costs no further request. The fragment is a
    full-screen CSS overlay. Called without a ``name`` it returns an empty body,
    which the overlay uses to close itself (clicking it clears the container).
    """
    names = [name for name in request.GET.getlist("name") if name]
    if not names:
        return HttpResponse("")  # Close: clear the modal container.
    cache = DbCardCache()
    if any(cache.get_image(name) is None for name in names):
        return HttpResponse("Image not found", status=404)
    return render(
        request,
        "partials/card_image_modal.html",
        {"image_urls": [f"/media/{name}" for name in names]},
    )
