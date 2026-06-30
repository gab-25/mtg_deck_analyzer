"""Tests for decklist parsing."""

from mtg_deck_analyzer.domain.decklist import parse_decklist, parse_decklist_text


def _write(tmp_path, contents):
    p = tmp_path / "deck.txt"
    p.write_text(contents, encoding="utf-8")
    return str(p)


def test_parses_quantity_and_name(tmp_path):
    path = _write(tmp_path, "4 Lightning Bolt\n2 Counterspell\n")
    cards = parse_decklist(path)
    assert cards == [
        {"quantity": 4, "name": "Lightning Bolt"},
        {"quantity": 2, "name": "Counterspell"},
    ]


def test_line_without_quantity_defaults_to_one(tmp_path):
    path = _write(tmp_path, "Sol Ring\n")
    assert parse_decklist(path) == [{"quantity": 1, "name": "Sol Ring"}]


def test_skips_blank_lines_and_comments(tmp_path):
    path = _write(tmp_path, "\n// a comment\n# another\n1 Island\n")
    assert parse_decklist(path) == [{"quantity": 1, "name": "Island"}]


def test_ignores_category_headers(tmp_path):
    path = _write(tmp_path, "Deck\n1 Forest\nSideboard\n2 Naturalize\nCommander\n")
    assert parse_decklist(path) == [
        {"quantity": 1, "name": "Forest"},
        {"quantity": 2, "name": "Naturalize"},
    ]


def test_category_header_match_is_case_insensitive(tmp_path):
    path = _write(tmp_path, "MAINBOARD\ncompanion\n1 Plains\n")
    assert parse_decklist(path) == [{"quantity": 1, "name": "Plains"}]


def test_strips_surrounding_whitespace(tmp_path):
    path = _write(tmp_path, "   3    Birds of Paradise   \n")
    assert parse_decklist(path) == [{"quantity": 3, "name": "Birds of Paradise"}]


def test_card_name_with_digits(tmp_path):
    path = _write(tmp_path, "1 Borrowing 100,000 Arrows\n")
    assert parse_decklist(path) == [
        {"quantity": 1, "name": "Borrowing 100,000 Arrows"}
    ]


def test_missing_file_returns_empty_list(tmp_path):
    missing = str(tmp_path / "does_not_exist.txt")
    assert parse_decklist(missing) == []


def test_empty_file_returns_empty_list(tmp_path):
    path = _write(tmp_path, "")
    assert parse_decklist(path) == []


def test_parse_decklist_text_parses_lines():
    cards = parse_decklist_text("4 Lightning Bolt\n// comment\n\n2 Island\n")
    assert cards == [
        {"quantity": 4, "name": "Lightning Bolt"},
        {"quantity": 2, "name": "Island"},
    ]


def test_parse_decklist_text_empty_returns_empty():
    assert parse_decklist_text("\n  \n# only comment\n") == []
