"""Who may see and change a deck: the single source of truth for both."""

import pytest
from django.contrib.auth.models import AnonymousUser

from mtg_deck_analyzer.access import can_edit, can_view, decks_visible_in_library
from mtg_deck_analyzer.models import Deck


@pytest.fixture
def owner(django_user_model):
    return django_user_model.objects.create_user(username="owner", password="pw")


@pytest.fixture
def stranger(django_user_model):
    return django_user_model.objects.create_user(username="stranger", password="pw")


def _deck(owner=None, visibility=Deck.Visibility.PRIVATE):
    return Deck.objects.create(
        name="A Deck",
        raw_decklist="1 Forest",
        owner=owner,
        visibility=visibility,
    )


@pytest.mark.django_db
def test_owner_may_view_and_edit_a_private_deck(owner):
    deck = _deck(owner=owner)
    assert can_view(owner, deck)
    assert can_edit(owner, deck)


@pytest.mark.django_db
def test_a_private_deck_is_invisible_to_everyone_else(owner, stranger):
    deck = _deck(owner=owner)
    assert not can_view(stranger, deck)
    assert not can_edit(stranger, deck)
    assert not can_view(AnonymousUser(), deck)
    assert not can_edit(AnonymousUser(), deck)


@pytest.mark.django_db
def test_an_unlisted_deck_is_readable_by_anyone_holding_the_link(owner, stranger):
    deck = _deck(owner=owner, visibility=Deck.Visibility.UNLISTED)
    assert can_view(stranger, deck)
    assert can_view(AnonymousUser(), deck)


@pytest.mark.django_db
def test_unlisted_grants_reading_only_never_writing(owner, stranger):
    deck = _deck(owner=owner, visibility=Deck.Visibility.UNLISTED)
    assert can_edit(owner, deck)
    assert not can_edit(stranger, deck)
    assert not can_edit(AnonymousUser(), deck)


@pytest.mark.django_db
def test_ownerless_legacy_decks_keep_their_old_behaviour(stranger):
    # Decks predating ownership belonged to every signed-in user; they still do.
    deck = _deck(owner=None)
    assert can_view(stranger, deck)
    assert can_edit(stranger, deck)
    assert not can_view(AnonymousUser(), deck)
    assert not can_edit(AnonymousUser(), deck)


@pytest.mark.django_db
def test_a_new_deck_is_private_by_default(owner):
    deck = Deck.objects.create(name="Fresh", raw_decklist="1 Forest", owner=owner)
    assert deck.visibility == Deck.Visibility.PRIVATE


@pytest.mark.django_db
def test_decks_visible_in_library_excludes_other_users_unlisted_decks(owner, stranger):
    """The one deliberate divergence from can_view: an unlisted deck is
    readable by anyone holding its link, but that must never make it show up
    in a browsing user's own library — only in the page a link points at.
    """
    unlisted_by_owner = _deck(owner=owner, visibility=Deck.Visibility.UNLISTED)
    strangers_own = _deck(owner=stranger)
    legacy = _deck(owner=None)

    visible = set(decks_visible_in_library(stranger).values_list("id", flat=True))
    assert strangers_own.id in visible
    assert legacy.id in visible
    assert unlisted_by_owner.id not in visible
