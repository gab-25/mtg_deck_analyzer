"""Tests for PDF generation: pure statistics, builders, and an end-to-end render."""

import pytest
from reportlab.platypus import Image as RLImage
from reportlab.platypus import Table

from mtg_deck_analyzer.pdf import (
    _build_card_image_cell,
    _build_styles,
    _compute_statistics,
    create_no_image_placeholder,
    create_stats_table,
    generate_pdf,
)


def _item(qty, type_line, price=0.0, cmc=0.0):
    return {
        "quantity": qty,
        "data": {
            "type_line": type_line,
            "price_eur": price,
            "cmc": cmc,
            "name": "Test Card",
            "faces": [{"name": "Test Card", "type_line": type_line, "rules_text": "Do a thing."}],
            "image_paths": [],
        },
    }


class TestComputeStatistics:
    def test_empty_deck(self):
        total, price, avg_cmc, counts = _compute_statistics([])
        assert total == 0
        assert price == 0.0
        assert avg_cmc == 0.0
        assert all(v == 0 for v in counts.values())

    def test_total_cards_sums_quantities(self):
        cards = [_item(4, "Creature"), _item(2, "Instant")]
        total, _, _, _ = _compute_statistics(cards)
        assert total == 6

    def test_total_price_weighted_by_quantity(self):
        cards = [_item(2, "Creature", price=1.50), _item(1, "Instant", price=3.00)]
        _, price, _, _ = _compute_statistics(cards)
        assert price == pytest.approx(2 * 1.50 + 3.00)

    def test_category_counts(self):
        cards = [_item(4, "Creature"), _item(3, "Land"), _item(1, "Sorcery")]
        _, _, _, counts = _compute_statistics(cards)
        assert counts["Creature"] == 4
        assert counts["Land"] == 3
        assert counts["Sorcery"] == 1

    def test_avg_cmc_excludes_lands(self):
        cards = [
            _item(2, "Creature", cmc=3.0),  # contributes 2*3 = 6 over 2 cards
            _item(4, "Land", cmc=0.0),      # excluded entirely
        ]
        _, _, avg_cmc, _ = _compute_statistics(cards)
        assert avg_cmc == pytest.approx(3.0)

    def test_avg_cmc_zero_when_only_lands(self):
        cards = [_item(10, "Land", cmc=0.0)]
        _, _, avg_cmc, _ = _compute_statistics(cards)
        assert avg_cmc == 0.0

    def test_avg_cmc_is_quantity_weighted(self):
        cards = [_item(3, "Creature", cmc=2.0), _item(1, "Sorcery", cmc=6.0)]
        # (3*2 + 1*6) / 4 = 3.0
        _, _, avg_cmc, _ = _compute_statistics(cards)
        assert avg_cmc == pytest.approx(3.0)


class TestPlaceholderAndImageCell:
    def test_placeholder_is_a_table(self):
        assert isinstance(create_no_image_placeholder(), Table)

    def test_no_images_yields_placeholder(self):
        cell = _build_card_image_cell([])
        assert isinstance(cell, Table)

    def test_single_image_path_yields_image(self, tmp_path):
        # A non-existent path: RLImage construction fails -> placeholder fallback.
        cell = _build_card_image_cell([str(tmp_path / "missing.jpg")])
        assert isinstance(cell, Table)  # placeholder

    def test_single_real_image_yields_rlimage(self, tmp_path):
        img = _make_png(tmp_path / "card.png")
        cell = _build_card_image_cell([img])
        assert isinstance(cell, RLImage)

    def test_two_images_yield_sub_table(self, tmp_path):
        a = _make_png(tmp_path / "a.png")
        b = _make_png(tmp_path / "b.png")
        cell = _build_card_image_cell([a, b])
        assert isinstance(cell, Table)


class TestBuildStyles:
    def test_contains_expected_keys(self):
        styles = _build_styles()
        for key in ("title", "subtitle", "h2", "h3", "body", "bullet", "card_title"):
            assert key in styles


class TestCreateStatsTable:
    def test_returns_table(self):
        table = create_stats_table(60, 123.45, 2.5, {"Creature": 20}, "Constructed")
        assert isinstance(table, Table)


class TestGeneratePdfEndToEnd:
    def test_produces_valid_pdf_file(self, tmp_path):
        cards = [
            _item(4, "Creature", price=0.50, cmc=2.0),
            _item(20, "Land", cmc=0.0),
            _item(2, "Instant", price=1.0, cmc=1.0),
        ]
        out = tmp_path / "deck.pdf"
        generate_pdf("My Test Deck", "## Strategy\n\nBe aggressive.", cards, str(out))

        assert out.exists()
        data = out.read_bytes()
        assert data.startswith(b"%PDF")
        assert len(data) > 1000

    def test_works_without_analysis(self, tmp_path):
        cards = [_item(1, "Creature")]
        out = tmp_path / "deck.pdf"
        generate_pdf("No Analysis Deck", None, cards, str(out))
        assert out.read_bytes().startswith(b"%PDF")


def _make_png(path):
    """Writes a minimal 1x1 PNG and returns its path as a string."""
    # Smallest valid 1x1 transparent PNG.
    png_bytes = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000a49444154789c6360000002000154a24f5f0000000049454e44ae426082"
    )
    path.write_bytes(png_bytes)
    return str(path)
