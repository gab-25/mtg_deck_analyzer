"""Django ORM models."""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from .domain.constants import DEFAULT_FORMAT, format_choices


class Deck(models.Model):
    """A submitted Commander deck together with its fetched cards and analysis."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    class Visibility(models.TextChoices):
        PRIVATE = "private", "Private"
        UNLISTED = "unlisted", "Unlisted"

    # UUID primary key so deck URLs aren't sequentially enumerable.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Who submitted the deck. NULL means only that the deck predates
    # ownership: those decks stay visible to every signed-in user, exactly
    # as they were before. Deleting a user deletes their decks and their
    # version history (CASCADE) rather than orphaning them to NULL, which
    # would otherwise make a deleted user's private decks readable and
    # writable by everyone.
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="decks",
    )

    # PRIVATE is owner-only; UNLISTED is readable by anyone holding the link.
    # No share token is needed: ``id`` is a UUID, so deck URLs aren't enumerable.
    visibility = models.CharField(
        max_length=16, choices=Visibility.choices, default=Visibility.PRIVATE
    )

    name = models.CharField(max_length=255)
    raw_decklist = models.TextField()

    # Which Commander format the deck is built for. It picks the ban list the
    # deck is validated against and the game the AI analysis assumes; deck
    # construction itself is identical across formats.
    format = models.CharField(
        max_length=16, choices=format_choices(), default=DEFAULT_FORMAT
    )

    # Lifecycle of the background analysis. Defaults to READY so decks created
    # directly (e.g. in tests/fixtures) need no extra handling; the async
    # creation flow sets PENDING explicitly and the worker advances it.
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.READY
    )
    # Populated with the failure reason when ``status`` is FAILED.
    error = models.TextField(null=True, blank=True)

    # Strategic analysis (GitHub-flavored Markdown), or NULL when unavailable.
    analysis_md = models.TextField(null=True, blank=True)

    # Commander identity: the commander's name (a one-element list, kept as a
    # list for the templates) and the WUBRG letters of the deck's color
    # identity (e.g. ``["W", "U"]``).
    commanders = models.JSONField(default=list)
    color_identity = models.JSONField(default=list)

    # Aggregate statistics.
    total_cards = models.IntegerField(default=0)
    total_value_eur = models.FloatField(default=0.0)
    category_counts = models.JSONField(default=dict)

    # The statistics panel, derived from ``cards`` at analysis time: mana
    # curve, pips against colored sources, the color-fixing verdict, the
    # functional role counts and the opening-hand odds. One JSON blob rather
    # than five columns, because nothing queries it — it is only ever read
    # whole. Empty for decks analyzed before it existed; the deck page
    # recomputes it for those.
    statistics = models.JSONField(default=dict)

    # Processed card list: ``[{"quantity": int, "is_commander": bool,
    # "data": {...}}]`` where each card's ``image_paths`` are stored as
    # cache-relative basenames.
    cards = models.JSONField(default=list)

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "decks"


class DeckVersion(models.Model):
    """One submitted decklist in a deck's history.

    Append-only: ``Deck.raw_decklist`` holds the current state, and these rows
    are the trail that says how it got there. Nothing here is ever rewritten,
    which is what makes "what did I cut when I added the second wheel?" a
    question the app can answer.
    """

    deck = models.ForeignKey(Deck, on_delete=models.CASCADE, related_name="versions")
    raw_decklist = models.TextField()

    # Optional one-line note the submitter attaches to a revision.
    note = models.CharField(max_length=255, blank=True, default="")

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "deck_versions"
        # Oldest first: a version is read against the one before it.
        ordering = ["created_at", "id"]


class ScryfallCard(models.Model):
    """Cached Scryfall card JSON, keyed by ``card_en_<slug>`` (the Scryfall cache)."""

    key = models.CharField(max_length=255, primary_key=True)
    data = models.JSONField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "scryfall_cards"


class ScryfallImage(models.Model):
    """Cached card image bytes, keyed by basename (``img_<id>_en.jpg``)."""

    name = models.CharField(max_length=255, primary_key=True)
    data = models.BinaryField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "scryfall_images"
