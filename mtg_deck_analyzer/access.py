"""Who may see and change a deck.

Every deck endpoint and every template flag comes from the two predicates
below, so the rule lives in one file instead of being re-derived at each of
the deck routes in ``urls.py``.
"""

from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.http import Http404
from django.shortcuts import get_object_or_404

from .models import Deck


def can_view(user, deck) -> bool:
    """Whether ``user`` may look at ``deck``.

    An unlisted deck is open to anyone holding the link — its UUID primary key
    is what keeps it unguessable. Everything else is owner-only, except the
    ownerless decks predating ownership, which stay readable by any signed-in
    user just as they were.
    """
    if deck.visibility == Deck.Visibility.UNLISTED:
        return True
    if not user.is_authenticated:
        return False
    return deck.owner_id is None or deck.owner_id == user.id


def can_edit(user, deck) -> bool:
    """Whether ``user`` may edit, re-analyze or delete ``deck``.

    Visibility never grants write access: an unlisted deck is readable by its
    link, not editable by it.
    """
    if not user.is_authenticated:
        return False
    return deck.owner_id is None or deck.owner_id == user.id


def _deck_access(predicate):
    """Builds a view decorator enforcing ``predicate`` on the addressed deck.

    The wrapped view is called with the resolved ``deck`` in place of the
    ``deck_id`` captured from the URL. A caller who may not proceed is sent to
    the login page when anonymous — so a signed-out owner lands back on the
    deck afterwards — and gets a 404 when signed in, which keeps a private
    deck's existence undisclosed.
    """

    def decorate(view):
        @wraps(view)
        def wrapper(request, deck_id, *args, **kwargs):
            deck = get_object_or_404(Deck, pk=deck_id)
            if predicate(request.user, deck):
                return view(request, deck, *args, **kwargs)
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            raise Http404("No deck matches the given query.")

        return wrapper

    return decorate


requires_deck_view = _deck_access(can_view)
requires_deck_edit = _deck_access(can_edit)
