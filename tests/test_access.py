"""Who may see and change a deck: the single source of truth for both."""

import pytest
from django.contrib.auth.models import AnonymousUser

from mtg_deck_analyzer.access import can_access, decks_visible_in_library
from mtg_deck_analyzer.models import Deck


@pytest.fixture
def owner(django_user_model):
    return django_user_model.objects.create_user(username="owner", password="pw")


@pytest.fixture
def stranger(django_user_model):
    return django_user_model.objects.create_user(username="stranger", password="pw")


def _deck(owner=None, name="A Deck"):
    return Deck.objects.create(name=name, raw_decklist="1 Forest", owner=owner)


@pytest.mark.django_db
def test_the_owner_may_open_and_change_their_deck(owner):
    assert can_access(owner, _deck(owner=owner))


@pytest.mark.django_db
def test_a_deck_is_invisible_to_everyone_else(owner, stranger):
    deck = _deck(owner=owner)
    assert not can_access(stranger, deck)
    assert not can_access(AnonymousUser(), deck)


@pytest.mark.django_db
def test_ownerless_legacy_decks_keep_their_old_behaviour(stranger):
    # Decks predating ownership belonged to every signed-in user; they still do.
    deck = _deck(owner=None)
    assert can_access(stranger, deck)
    assert not can_access(AnonymousUser(), deck)


@pytest.mark.django_db
def test_the_library_lists_your_own_decks_and_the_legacy_ones_only(owner, stranger):
    mine = _deck(owner=owner, name="Mine")
    theirs = _deck(owner=stranger, name="Theirs")
    legacy = _deck(owner=None, name="Legacy")

    visible = set(decks_visible_in_library(owner).values_list("id", flat=True))
    assert mine.id in visible
    assert legacy.id in visible
    assert theirs.id not in visible


@pytest.mark.django_db
def test_the_library_filter_agrees_with_the_predicate(owner, stranger):
    """The queryset is the filter form of ``can_access``; they must not drift.

    A deck the predicate admits has to be listed, and one it refuses must not
    be — otherwise the library and the endpoints would disagree about the
    same deck.
    """
    decks = [_deck(owner=owner), _deck(owner=stranger), _deck(owner=None)]
    listed = set(decks_visible_in_library(owner).values_list("id", flat=True))

    for deck in decks:
        assert (deck.id in listed) == can_access(owner, deck)
