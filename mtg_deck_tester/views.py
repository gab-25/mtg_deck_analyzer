"""The home page: recent matches and decks at a glance."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from decks.models import Deck
from decks.presentation import deck_pips
from playtest.agents import openrouter
from playtest.models import Match

RECENT = 6


@login_required
@require_http_methods(["GET"])
def home(request):
    matches = list(
        Match.objects.filter(owner=request.user)
        .select_related("winner")
        .prefetch_related("seats")[:RECENT]
    )
    decks = list(Deck.objects.filter(owner=request.user)[:RECENT])
    for deck in decks:
        deck.pips = deck_pips(deck)
    return render(
        request,
        "home.html",
        {
            "matches": matches,
            "decks": decks,
            "deck_count": Deck.objects.filter(owner=request.user).count(),
            "match_count": Match.objects.filter(owner=request.user).count(),
            "llm_ready": openrouter.api_key() is not None,
        },
    )
