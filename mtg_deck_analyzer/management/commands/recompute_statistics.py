"""Refills stored deck statistics after a STATISTICS_SCHEMA bump."""

from django.core.management.base import BaseCommand

from ...domain.statistics import STATISTICS_SCHEMA, deck_statistics
from ...models import Deck


class Command(BaseCommand):
    help = "Recompute stored deck statistics whose schema is out of date."

    def add_arguments(self, parser):
        parser.add_argument(
            "--all",
            action="store_true",
            help="Recompute every deck, not only the ones with a stale blob.",
        )

    def handle(self, *args, **options):
        rewritten = 0
        for deck in Deck.objects.iterator():
            cards = deck.cards or []
            # Nothing to compute from: an analysis that never finished, or
            # one that failed. Storing an empty-deck blob would put a panel
            # of zeroes on a page that currently shows none.
            if not cards:
                continue
            stored = deck.statistics or {}
            if not options["all"] and stored.get("schema") == STATISTICS_SCHEMA:
                continue
            deck.statistics = deck_statistics(cards)
            deck.save(update_fields=["statistics"])
            rewritten += 1

        self.stdout.write(f"Recomputed statistics for {rewritten} deck(s).")
