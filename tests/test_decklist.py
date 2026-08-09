"""Tests for decklist parsing."""

from mtg_deck_analyzer.domain.decklist import parse_decklist, parse_decklist_text


def _write(tmp_path, contents):
    p = tmp_path / "deck.txt"
    p.write_text(contents, encoding="utf-8")
    return str(p)


def _card(qty, name, is_commander=False):
    return {"quantity": qty, "name": name, "is_commander": is_commander}


def test_parses_quantity_and_name(tmp_path):
    path = _write(tmp_path, "4 Lightning Bolt\n2 Counterspell\n")
    cards = parse_decklist(path)
    assert cards == [_card(4, "Lightning Bolt"), _card(2, "Counterspell")]


def test_parses_the_x_quantity_spelling(tmp_path):
    path = _write(tmp_path, "1x Sol Ring\n12x Forest\n")
    assert parse_decklist(path) == [_card(1, "Sol Ring"), _card(12, "Forest")]


def test_line_without_quantity_defaults_to_one(tmp_path):
    path = _write(tmp_path, "Sol Ring\n")
    assert parse_decklist(path) == [_card(1, "Sol Ring")]


def test_skips_blank_lines_and_comments(tmp_path):
    path = _write(tmp_path, "\n// a comment\n# another\n1 Island\n")
    assert parse_decklist(path) == [_card(1, "Island")]


def test_commander_section_flags_its_cards(tmp_path):
    path = _write(
        tmp_path,
        "Commander\n1 Atraxa, Praetors' Voice\n\nDeck\n1 Sol Ring\n",
    )
    assert parse_decklist(path) == [
        _card(1, "Atraxa, Praetors' Voice", is_commander=True),
        _card(1, "Sol Ring"),
    ]


def test_cmdr_marker_flags_a_single_line(tmp_path):
    path = _write(tmp_path, "1 Atraxa, Praetors' Voice *CMDR*\n1 Sol Ring\n")
    assert parse_decklist(path) == [
        _card(1, "Atraxa, Praetors' Voice", is_commander=True),
        _card(1, "Sol Ring"),
    ]


def test_sideboard_cards_still_count_towards_the_deck(tmp_path):
    # Commander has no sideboard: the header is skipped but its cards are kept,
    # so the 100-card rule catches the overflow.
    path = _write(tmp_path, "Deck\n1 Forest\nSideboard\n2 Naturalize\n")
    assert parse_decklist(path) == [_card(1, "Forest"), _card(2, "Naturalize")]


def test_section_header_match_is_case_insensitive(tmp_path):
    path = _write(tmp_path, "MAINBOARD\n1 Plains\ncommander:\n1 Ramos, Dragon Engine\n")
    assert parse_decklist(path) == [
        _card(1, "Plains"),
        _card(1, "Ramos, Dragon Engine", is_commander=True),
    ]


def test_strips_surrounding_whitespace(tmp_path):
    path = _write(tmp_path, "   3    Birds of Paradise   \n")
    assert parse_decklist(path) == [_card(3, "Birds of Paradise")]


def test_card_name_with_digits(tmp_path):
    path = _write(tmp_path, "1 Borrowing 100,000 Arrows\n")
    assert parse_decklist(path) == [_card(1, "Borrowing 100,000 Arrows")]


def test_missing_file_returns_empty_list(tmp_path):
    missing = str(tmp_path / "does_not_exist.txt")
    assert parse_decklist(missing) == []


def test_empty_file_returns_empty_list(tmp_path):
    path = _write(tmp_path, "")
    assert parse_decklist(path) == []


def test_parse_decklist_text_parses_lines():
    cards = parse_decklist_text("4 Lightning Bolt\n// comment\n\n2 Island\n")
    assert cards == [_card(4, "Lightning Bolt"), _card(2, "Island")]


def test_parse_decklist_text_empty_returns_empty():
    assert parse_decklist_text("\n  \n# only comment\n") == []
