"""Tests for PDF generation: pure statistics, builders, and an end-to-end render."""

import pytest
from reportlab.platypus import Image as RLImage
from reportlab.platypus import Table

from mtg_deck_analyzer.domain.cards import compute_statistics as _compute_statistics
from mtg_deck_analyzer.rendering.pdf import (
    _build_card_image_cell,
    _build_styles,
    create_no_image_placeholder,
    create_stats_table,
    create_statistics_flowables,
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

    def test_single_file_like_stream_yields_rlimage(self, tmp_path):
        # The web app feeds in-memory BytesIO streams (images read from the DB).
        import io

        png_bytes = (tmp_path / "card.png")
        _make_png(png_bytes)
        cell = _build_card_image_cell([io.BytesIO(png_bytes.read_bytes())])
        assert isinstance(cell, RLImage)

    def test_two_images_yield_both_faces_side_by_side(self, tmp_path):
        a = _make_png(tmp_path / "a.png")
        b = _make_png(tmp_path / "b.png")
        cell = _build_card_image_cell([a, b])
        # A plain `isinstance(cell, Table)` would also pass for the placeholder,
        # so reach into the sub-table: one row, both faces, both real images.
        assert isinstance(cell, Table)
        row = cell._cellvalues[0]
        assert len(cell._cellvalues) == 1
        assert [type(c) for c in row] == [RLImage, RLImage]
        # Each face is drawn at the smaller two-up size, not the single-card one.
        assert [(c.drawWidth, c.drawHeight) for c in row] == [(80, 112), (80, 112)]

    def test_a_missing_second_face_still_leaves_the_first_one_drawn(self, tmp_path):
        a = _make_png(tmp_path / "a.png")
        cell = _build_card_image_cell([a, str(tmp_path / "missing.jpg")])
        row = cell._cellvalues[0]
        assert isinstance(row[0], RLImage)
        assert isinstance(row[1], Table)  # placeholder in the back-face slot


class TestBuildStyles:
    def test_contains_expected_keys(self):
        styles = _build_styles()
        for key in ("title", "subtitle", "h2", "h3", "body", "bullet", "card_title"):
            assert key in styles


def _stats_text(table) -> str:
    """All paragraph text inside a stats table, flattened."""

    def walk(tbl, out):
        for row in tbl._cellvalues:
            for cell in row:
                if hasattr(cell, "_cellvalues"):
                    walk(cell, out)
                elif hasattr(cell, "text"):
                    out.append(cell.text)
        return out

    return " ".join(walk(table, []))


class TestCreateStatsTable:
    def test_returns_table(self):
        table = create_stats_table(100, 123.45, 2.5, {"Creature": 20})
        assert isinstance(table, Table)

    def test_returns_table_with_commanders(self):
        table = create_stats_table(
            100, 123.45, 2.5, {"Creature": 20}, ["Atraxa, Praetors' Voice"]
        )
        assert isinstance(table, Table)

    def test_prints_commander_by_default(self):
        table = create_stats_table(100, 123.45, 2.5, {"Creature": 20})
        assert "<b>Format:</b> Commander" in _stats_text(table)

    def test_prints_the_decks_format(self):
        table = create_stats_table(100, 123.45, 2.5, {"Creature": 20}, fmt="duel")
        assert "<b>Format:</b> Duel Commander" in _stats_text(table)


class TestGeneratePdfEndToEnd:
    def test_produces_valid_pdf_file(self, tmp_path):
        cards = [
            _item(4, "Creature", price=0.50, cmc=2.0),
            _item(20, "Land", cmc=0.0),
            _item(2, "Instant", price=1.0, cmc=1.0),
        ]
        out = tmp_path / "deck.pdf"
        generate_pdf(
            "My Test Deck",
            "## Strategy\n\nBe aggressive.",
            cards,
            str(out),
            commanders=["Atraxa, Praetors' Voice"],
        )

        assert out.exists()
        data = out.read_bytes()
        assert data.startswith(b"%PDF")
        assert len(data) > 1000

    def test_works_without_analysis(self, tmp_path):
        cards = [_item(1, "Creature")]
        out = tmp_path / "deck.pdf"
        generate_pdf("No Analysis Deck", None, cards, str(out))
        assert out.read_bytes().startswith(b"%PDF")


class TestStatisticsSection:
    def _statistics(self):
        from mtg_deck_analyzer.domain.statistics import deck_statistics
        return deck_statistics([
            {"quantity": 30, "is_commander": False,
             "data": {"name": "Island", "type_line": "Basic Land — Island",
                      "cmc": 0.0, "produced_mana": ["U"],
                      "faces": [{"name": "Island", "mana_cost": "",
                                 "type_line": "Basic Land — Island",
                                 "rules_text": "{T}: Add {U}."}]}},
            {"quantity": 40, "is_commander": False,
             "data": {"name": "Counterspell", "type_line": "Instant",
                      "cmc": 2.0, "produced_mana": [], "color_identity": ["U"],
                      "faces": [{"name": "Counterspell", "mana_cost": "{U}{U}",
                                 "type_line": "Instant", "rules_text": ""}]}},
            {"quantity": 29, "is_commander": False,
             "data": {"name": "Bear", "type_line": "Creature — Bear",
                      "cmc": 3.0, "produced_mana": [], "color_identity": ["U"],
                      "faces": [{"name": "Bear", "mana_cost": "{2}{U}",
                                 "type_line": "Creature — Bear",
                                 "rules_text": ""}]}},
        ])

    def test_the_section_is_built_from_the_statistics(self):
        flowables = create_statistics_flowables(self._statistics(), _build_styles())
        assert flowables
        assert any(isinstance(f, Table) for f in flowables)

    def test_an_empty_deck_yields_no_section(self):
        from mtg_deck_analyzer.domain.statistics import deck_statistics
        assert create_statistics_flowables(deck_statistics([]), _build_styles()) == []

    def test_the_curve_row_separates_permanents_from_spells(self):
        flowables = create_statistics_flowables(self._statistics(), _build_styles())
        # Text lives either on a bare Paragraph flowable or inside a Table cell.
        texts = [getattr(f, "text", "") for f in flowables]
        texts += [getattr(cell, "text", "") for f in flowables
                  for row in getattr(f, "_cellvalues", []) for cell in row]
        assert any("Permanents" in t for t in texts)
        assert any("Spells" in t for t in texts)

    def test_generate_pdf_includes_the_section(self, tmp_path):
        out = tmp_path / "deck.pdf"
        generate_pdf("Test Deck", None, [_item(1, "Creature — Bear", cmc=2.0)],
                     str(out), statistics=self._statistics())
        assert out.stat().st_size > 0

    def test_generate_pdf_recomputes_when_given_none(self, tmp_path):
        out = tmp_path / "deck.pdf"
        generate_pdf("Test Deck", None, [_item(1, "Creature — Bear", cmc=2.0)],
                     str(out))
        assert out.exists()


def _make_png(path):
    """Writes a minimal 1x1 PNG and returns its path as a string."""
    # Smallest valid 1x1 transparent PNG.
    png_bytes = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000a49444154789c6360000002000154a24f5f0000000049454e44ae426082"
    )
    path.write_bytes(png_bytes)
    return str(path)
