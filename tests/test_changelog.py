"""The changelog between two submitted decklists."""

from mtg_deck_analyzer.domain.changelog import decklist_changes


def test_no_difference_produces_no_changelog():
    text = "Commander\n1 Atraxa, Praetors' Voice\n\nDeck\n1 Sol Ring"
    assert decklist_changes(text, text) == []


def test_a_swapped_card_reads_as_an_addition_and_a_removal():
    before = "1 Arcane Signet\n1 Sol Ring"
    after = "1 Rhystic Study\n1 Sol Ring"
    assert decklist_changes(before, after) == [
        {"sign": "+", "quantity": 1, "name": "Rhystic Study"},
        {"sign": "-", "quantity": 1, "name": "Arcane Signet"},
    ]


def test_additions_come_first_then_removals_each_alphabetical():
    before = "1 Zur's Weirding\n1 Ancestral Recall"
    after = "1 Brainstorm\n1 Ancient Tomb"
    assert decklist_changes(before, after) == [
        {"sign": "+", "quantity": 1, "name": "Ancient Tomb"},
        {"sign": "+", "quantity": 1, "name": "Brainstorm"},
        {"sign": "-", "quantity": 1, "name": "Ancestral Recall"},
        {"sign": "-", "quantity": 1, "name": "Zur's Weirding"},
    ]


def test_a_changed_count_is_reported_as_the_difference_only():
    # 38 Forest -> 40 Forest is "+2 Forest", not "+40 / -38".
    assert decklist_changes("38 Forest", "40 Forest") == [
        {"sign": "+", "quantity": 2, "name": "Forest"}
    ]
    assert decklist_changes("40 Forest", "38 Forest") == [
        {"sign": "-", "quantity": 2, "name": "Forest"}
    ]


def test_copies_of_the_same_card_on_several_lines_are_summed():
    assert decklist_changes("1 Forest\n1 Forest", "1 Forest") == [
        {"sign": "-", "quantity": 1, "name": "Forest"}
    ]


def test_the_commander_counts_like_any_other_card():
    before = "Commander\n1 Atraxa, Praetors' Voice\n\nDeck\n1 Sol Ring"
    after = "Commander\n1 Kenrith, the Returned King\n\nDeck\n1 Sol Ring"
    assert decklist_changes(before, after) == [
        {"sign": "+", "quantity": 1, "name": "Kenrith, the Returned King"},
        {"sign": "-", "quantity": 1, "name": "Atraxa, Praetors' Voice"},
    ]


def test_moving_a_card_between_sections_is_not_a_change():
    # A card promoted to the commander section is the same card in the same
    # count: the decklist diff has nothing to report.
    before = "Deck\n1 Atraxa, Praetors' Voice\n1 Sol Ring"
    after = "Commander\n1 Atraxa, Praetors' Voice\n\nDeck\n1 Sol Ring"
    assert decklist_changes(before, after) == []


def test_an_empty_previous_list_reports_everything_as_added():
    assert decklist_changes("", "2 Forest") == [
        {"sign": "+", "quantity": 2, "name": "Forest"}
    ]


def test_the_same_card_with_different_casing_produces_no_change():
    # Same card, different casing — should be treated as the same card.
    assert decklist_changes("1 Sol Ring", "1 sol ring") == []


def test_a_double_faced_card_spelled_two_ways_produces_no_change():
    # Delver of Secrets // Insectile Aberration and Delver of Secrets are the same card.
    before = "1 Delver of Secrets // Insectile Aberration"
    after = "1 Delver of Secrets"
    assert decklist_changes(before, after) == []


def test_a_card_with_changed_count_spelled_differently_reports_a_single_delta():
    # Changed count with different casing should report one delta, not add + remove.
    # The CURRENT (newer) list's spelling should be used.
    assert decklist_changes("38 FOREST", "40 Forest") == [
        {"sign": "+", "quantity": 2, "name": "Forest"}
    ]


def test_a_removed_card_uses_its_previous_spelling_despite_casing_elsewhere():
    # When a card with changed spelling is removed, it displays with the
    # previous spelling. This test involves a casing-variant collision:
    # forest/FOREST are the same card (normalized), so they should not appear
    # in the changelog, but ARCANE SIGNET (which is removed) should display
    # with its original spelling from the previous list.
    before = "1 ARCANE SIGNET\n1 forest"
    after = "1 FOREST\n1 Sol Ring"
    assert decklist_changes(before, after) == [
        {"sign": "+", "quantity": 1, "name": "Sol Ring"},
        {"sign": "-", "quantity": 1, "name": "ARCANE SIGNET"},
    ]
