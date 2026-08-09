"""Django ORM models."""

import uuid

from django.db import models
from django.utils import timezone


class Deck(models.Model):
    """A submitted Commander deck together with its fetched cards and analysis."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    # UUID primary key so deck URLs aren't sequentially enumerable.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    name = models.CharField(max_length=255)
    raw_decklist = models.TextField()

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
    avg_cmc = models.FloatField(default=0.0)
    category_counts = models.JSONField(default=dict)

    # Processed card list: ``[{"quantity": int, "is_commander": bool,
    # "data": {...}}]`` where each card's ``image_paths`` are stored as
    # cache-relative basenames.
    cards = models.JSONField(default=list)

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "decks"


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
