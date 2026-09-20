"""Tests for the hypergeometric primitives behind the deck statistics."""

import pytest

from mtg_deck_analyzer.domain.probability import at_least, exactly, min_successes_for


class TestExactly:
    def test_textbook_value(self):
        # Two successes in a four-card urn, both drawn in two draws: 1 in 6.
        assert exactly(4, 2, 2, 2) == pytest.approx(1 / 6)

    def test_more_successes_than_exist_is_impossible(self):
        assert exactly(10, 2, 5, 3) == 0.0

    def test_more_successes_than_draws_is_impossible(self):
        assert exactly(10, 5, 2, 3) == 0.0

    def test_too_few_failures_left_is_impossible(self):
        # Nine of the ten cards are successes: eight draws cannot yield one.
        assert exactly(10, 9, 8, 1) == 0.0

    def test_distribution_sums_to_one(self):
        total = sum(exactly(99, 38, 7, k) for k in range(8))
        assert total == pytest.approx(1.0)

    def test_empty_population_draws_nothing(self):
        assert exactly(0, 0, 7, 0) == 1.0
        assert exactly(0, 0, 7, 1) == 0.0


class TestAtLeast:
    def test_at_least_zero_is_certain(self):
        assert at_least(99, 38, 7, 0) == 1.0

    def test_four_copies_in_sixty_cards(self):
        # The classic "one of four in the opening seven" number.
        assert at_least(60, 4, 7, 1) == pytest.approx(0.3995, abs=1e-4)

    def test_is_the_tail_of_exactly(self):
        expected = sum(exactly(99, 38, 7, k) for k in range(3, 8))
        assert at_least(99, 38, 7, 3) == pytest.approx(expected)

    def test_drawing_more_than_the_library_is_clamped(self):
        # Ten cards drawn from a five-card library: every card is seen.
        assert at_least(5, 2, 10, 2) == 1.0


class TestMinSuccessesFor:
    def test_karsten_style_single_pip_on_turn_one(self):
        # 99-card library, opening seven, 90% confidence.
        assert min_successes_for(99, 7, 1, 0.90) == 27

    def test_karsten_style_double_pip_on_turn_two(self):
        assert min_successes_for(99, 8, 2, 0.90) == 40

    def test_more_draws_lower_the_requirement(self):
        assert min_successes_for(99, 9, 1, 0.90) < min_successes_for(99, 7, 1, 0.90)

    def test_zero_required_needs_nothing(self):
        assert min_successes_for(99, 7, 0, 0.90) == 0

    def test_unreachable_target_is_none(self):
        # Two cards must show up in a single draw: no copy count can do it.
        assert min_successes_for(99, 1, 2, 0.90) is None
