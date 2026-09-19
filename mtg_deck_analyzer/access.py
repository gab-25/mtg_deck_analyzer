"""Who may see and change a deck.

Every deck endpoint comes from the rule below, so access lives in one file
instead of being re-derived at each of the deck routes in ``urls.py``.

A deck is its owner's alone: seeing it and changing it are the same
permission, so there is one predicate rather than a read/write pair.
"""

from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.db.models import Q, QuerySet
from django.http import Http404
from django.shortcuts import get_object_or_404

from .models import Deck


def can_access(user, deck) -> bool:
    """Whether ``user`` may open, edit, re-analyze or delete ``deck``.

    Owner-only, with one carve-out: the ownerless decks that predate
    ownership stay available to any signed-in user, exactly as they were
    before this existed.
    """
    if not user.is_authenticated:
        return False
    return deck.owner_id is None or deck.owner_id == user.id


def decks_visible_in_library(user) -> QuerySet:
    """The decks ``user``'s library page may list.

    The queryset form of :func:`can_access`, for the one caller that needs
    the rule as a filter rather than a yes/no on a deck it already holds.
    """
    return Deck.objects.filter(Q(owner=user) | Q(owner__isnull=True))


def requires_deck_access(view):
    """View decorator enforcing :func:`can_access` on the addressed deck.

    The wrapped view is called with the resolved ``deck`` in place of the
    ``deck_id`` captured from the URL. A caller who may not proceed is sent to
    the login page when anonymous — so a signed-out owner lands back on the
    deck afterwards — and gets a 404 when signed in, which keeps another
    user's deck undisclosed rather than confirming it exists.
    """

    @wraps(view)
    def wrapper(request, deck_id, *args, **kwargs):
        deck = get_object_or_404(Deck, pk=deck_id)
        if can_access(request.user, deck):
            return view(request, deck, *args, **kwargs)
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        raise Http404("No deck matches the given query.")

    return wrapper
