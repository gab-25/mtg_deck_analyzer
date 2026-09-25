"""Tests for running a stored match through the engine."""

import pytest

from playtest.engine.cards import Kind
from playtest.models import Match, MatchEvent, Seat
from playtest.runner import card_spec, deck_spec, run_match

from .factories import make_deck, scryfall_card, stored_cards


@pytest.mark.parametrize(
    "type_line, kind",
    [
        ("Basic Land — Forest", Kind.LAND),
        ("Legendary Creature — Elf", Kind.CREATURE),
        ("Artifact", Kind.PERMANENT),
        ("Legendary Planeswalker — Jace", Kind.PERMANENT),
        ("Instant", Kind.SPELL),
        ("Sorcery", Kind.SPELL),
    ],
)
def test_card_spec_maps_the_card_type(type_line, kind):
    assert card_spec(scryfall_card("X", type_line)).kind == kind


@pytest.mark.parametrize("power, expected", [("3", 3), ("1+*", 1), ("*", 0), (None, 0)])
def test_card_spec_reads_printed_power(power, expected):
    assert card_spec(scryfall_card("X", "Creature", power=power)).power == expected


def test_deck_spec_expands_quantities_and_separates_the_commander():
    spec = deck_spec("Bears", stored_cards())
    assert spec.commander.name == "Bear Lord"
    assert len(spec.library) == 99


def test_deck_spec_requires_a_commander():
    cards = [item for item in stored_cards() if not item["is_commander"]]
    with pytest.raises(ValueError, match="no commander"):
        deck_spec("Bears", cards)


def _match(user, fmt="duel", seats=2, **fields):
    match = Match.objects.create(owner=user, format=fmt, seed=5, **fields)
    for position in range(seats):
        deck = make_deck(user, name=f"Deck {position}", fmt=fmt)
        Seat.objects.create(match=match, position=position, deck=deck, deck_name=deck.name)
    return match


@pytest.mark.django_db
def test_run_match_stores_the_log_and_the_result(django_user_model):
    user = django_user_model.objects.create_user(username="u")
    match = _match(user, max_rounds=40)
    run_match(match.id)

    match.refresh_from_db()
    assert match.status == Match.Status.FINISHED
    assert match.finished_at is not None
    events = list(MatchEvent.objects.filter(match=match))
    assert events[0].kind == "setup"
    assert events[-1].kind == "game_over"
    assert [e.seq for e in events] == list(range(1, len(events) + 1))
    seats = list(match.seats.all())
    assert all(seat.life is not None for seat in seats)
    if match.end_reason == Match.EndReason.LAST_STANDING:
        assert match.winner in seats


@pytest.mark.django_db
def test_run_match_is_reproducible(django_user_model):
    user = django_user_model.objects.create_user(username="u")
    logs = []
    for _ in range(2):
        match = _match(user, max_rounds=10)
        run_match(match.id)
        logs.append(list(match.events.values_list("text", flat=True)))
    assert logs[0] == logs[1]


@pytest.mark.django_db
def test_a_match_whose_deck_was_deleted_fails_cleanly(django_user_model):
    user = django_user_model.objects.create_user(username="u")
    match = _match(user)
    match.seats.first().deck.delete()
    run_match(match.id)
    match.refresh_from_db()
    assert match.status == Match.Status.FAILED
    assert "deleted" in match.error
