"""Tests for text utilities and Markdown conversion."""

from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import HRFlowable, Paragraph, Spacer

from mtg_deck_analyzer.text_utils import (
    convert_markdown_inline,
    escape_for_paragraph,
    get_card_slug,
    localize_card_names,
    markdown_to_flowables,
    slugify,
)


class TestSlug:
    def test_lowercases_and_replaces_non_alnum(self):
        assert get_card_slug("Lightning Bolt") == "lightning_bolt"

    def test_strips_leading_trailing_underscores(self):
        assert get_card_slug("!!! Wrath !!!") == "wrath"

    def test_collapses_runs_of_separators(self):
        assert get_card_slug("Jace, the Mind Sculptor") == "jace_the_mind_sculptor"

    def test_keeps_digits(self):
        assert get_card_slug("Borrowing 100000 Arrows") == "borrowing_100000_arrows"

    def test_slugify_is_alias_of_get_card_slug(self):
        assert slugify("Sol Ring") == get_card_slug("Sol Ring")


class TestEscapeForParagraph:
    def test_empty_returns_empty(self):
        assert escape_for_paragraph("") == ""
        assert escape_for_paragraph(None) == ""

    def test_escapes_html_special_chars(self):
        assert escape_for_paragraph("a < b & c") == "a &lt; b &amp; c"

    def test_newlines_become_br(self):
        assert escape_for_paragraph("line1\nline2") == "line1<br/>line2"


class TestConvertMarkdownInline:
    def test_bold(self):
        assert convert_markdown_inline("**hi**") == "<b>hi</b>"

    def test_italic_star_and_underscore(self):
        assert convert_markdown_inline("*hi*") == "<i>hi</i>"
        assert convert_markdown_inline("_hi_") == "<i>hi</i>"

    def test_inline_code(self):
        assert convert_markdown_inline("`x`") == '<font face="Courier">x</font>'

    def test_escapes_html_before_styling(self):
        # The angle brackets must be escaped, not treated as tags.
        assert convert_markdown_inline("a < b") == "a &lt; b"

    def test_bold_takes_precedence_over_italic(self):
        assert convert_markdown_inline("**bold**") == "<b>bold</b>"


def _make_styles():
    base = getSampleStyleSheet()
    return {
        "Heading1": base["Heading1"],
        "Heading2": base["Heading2"],
        "Heading3": base["Heading3"],
        "Normal": base["Normal"],
        "Bullet": ParagraphStyle("Bullet", parent=base["Normal"]),
    }


class TestMarkdownToFlowables:
    styles = _make_styles()

    def _types(self, flowables):
        return [type(f) for f in flowables]

    def test_empty_text_yields_no_flowables(self):
        assert markdown_to_flowables("", self.styles) == []

    def test_paragraph_produces_paragraph_and_spacer(self):
        out = markdown_to_flowables("Just some text.", self.styles)
        assert self._types(out) == [Paragraph, Spacer]

    def test_horizontal_rule_renders_divider(self):
        out = markdown_to_flowables("---", self.styles)
        assert any(isinstance(f, HRFlowable) for f in out)
        assert not any(isinstance(f, Paragraph) for f in out)

    def test_heading_uses_matching_style(self):
        out = markdown_to_flowables("## Title", self.styles)
        paragraphs = [f for f in out if isinstance(f, Paragraph)]
        assert len(paragraphs) == 1
        assert paragraphs[0].style.name == "Heading2"

    def test_heading_level_capped_at_three(self):
        out = markdown_to_flowables("#### Deep", self.styles)
        paragraphs = [f for f in out if isinstance(f, Paragraph)]
        assert paragraphs[0].style.name == "Heading3"

    def test_bullet_list_one_paragraph_per_item(self):
        out = markdown_to_flowables("- one\n- two\n- three", self.styles)
        paragraphs = [f for f in out if isinstance(f, Paragraph)]
        assert len(paragraphs) == 3
        assert all(p.style.name == "Bullet" for p in paragraphs)

    def test_numbered_list_keeps_number_prefix(self):
        out = markdown_to_flowables("1. first\n2. second", self.styles)
        paragraphs = [f for f in out if isinstance(f, Paragraph)]
        assert len(paragraphs) == 2

    def test_double_newline_splits_paragraphs(self):
        out = markdown_to_flowables("First para.\n\nSecond para.", self.styles)
        paragraphs = [f for f in out if isinstance(f, Paragraph)]
        assert len(paragraphs) == 2

    def test_heading_followed_by_body_on_next_line_splits(self):
        # A heading line immediately followed by body text (single newline) must
        # not render the whole block at heading size.
        out = markdown_to_flowables("## Title\nBody text here.", self.styles)
        paragraphs = [f for f in out if isinstance(f, Paragraph)]
        assert len(paragraphs) == 2
        assert paragraphs[0].style.name == "Heading2"
        assert paragraphs[0].text == "Title"
        assert paragraphs[1].style.name == "Normal"
        assert "Body text here." in paragraphs[1].text


class TestLocalizeCardNames:
    def test_replaces_card_name(self):
        out = localize_card_names("Play **Forest** now.", {"Forest": "Foresta"})
        assert out == "Play **Foresta** now."

    def test_longer_name_wins_over_prefix(self):
        name_map = {
            "Tatyova": "WRONG",
            "Tatyova, Benthic Druid": "Tatyova, Druido Bentonico",
        }
        out = localize_card_names("**Tatyova, Benthic Druid** leads.", name_map)
        assert out == "**Tatyova, Druido Bentonico** leads."

    def test_respects_word_boundaries(self):
        out = localize_card_names("Forestwalk is not a Forest.", {"Forest": "Foresta"})
        assert out == "Forestwalk is not a Foresta."

    def test_case_insensitive(self):
        out = localize_card_names("a sol ring", {"Sol Ring": "Anello Solare"})
        assert out == "a Anello Solare"

    def test_skips_identical_names(self):
        out = localize_card_names("Sol Ring rules", {"Sol Ring": "Sol Ring"})
        assert out == "Sol Ring rules"

    def test_empty_inputs(self):
        assert localize_card_names("", {"Forest": "Foresta"}) == ""
        assert localize_card_names("text", {}) == "text"
