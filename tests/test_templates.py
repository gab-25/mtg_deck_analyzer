"""Structural checks over the templates themselves."""

import re
from pathlib import Path

import pytest

TEMPLATES = Path(__file__).resolve().parent.parent / "mtg_deck_analyzer" / "templates"


def _template_files():
    return sorted(TEMPLATES.rglob("*.html"))


def _unterminated_hash_comments(source: str) -> list:
    """Line numbers where a ``{#`` has no ``#}`` on the same line.

    Django's hash comment is single-line only: a ``{#`` whose ``#}`` sits on a
    later line is not a comment at all, and the whole thing is rendered to the
    page verbatim.
    """
    offending = []
    for match in re.finditer(r"\{#", source):
        start = match.start()
        end_of_line = source.find("\n", start)
        end_of_line = len(source) if end_of_line == -1 else end_of_line
        close = source.find("#}", start)
        if close == -1 or close > end_of_line:
            offending.append(source.count("\n", 0, start) + 1)
    return offending


@pytest.mark.parametrize("path", _template_files(), ids=lambda p: p.name)
def test_hash_comments_stay_on_one_line(path):
    """A multi-line ``{# #}`` leaks its own text into the rendered page.

    Django only strips a hash comment that opens and closes on the same line.
    Spread one over several lines and the reader sees the note meant for the
    next developer printed above the page. Multi-line notes belong in
    ``{% comment %}`` / ``{% endcomment %}``, which the rest of the templates
    already use.
    """
    lines = _unterminated_hash_comments(path.read_text())
    assert not lines, (
        f"{path.name} has a {{# #}} comment spanning several lines at "
        f"line(s) {lines}; use {{% comment %}} instead or it will render."
    )


def test_the_scan_itself_detects_a_multi_line_comment():
    """Guards the check above: a scanner that never fires proves nothing."""
    assert _unterminated_hash_comments("{# one line #}\n") == []
    assert _unterminated_hash_comments("{# first\n   second #}\n") == [1]


STYLES = (
    Path(__file__).resolve().parent.parent / "theme" / "static" / "css" / "styles.css"
)

#: Class attribute of an element whose grid has a hard-coded column width.
FIXED_COLUMN_GRID = re.compile(r'class="([^"]*\bgrid-cols-\[[^\]]*\d+px[^\]]*\][^"]*)"')


def _mobile_collapse_classes() -> set:
    """Classes a narrow-viewport media query folds into a single column."""
    source = STYLES.read_text()
    classes = set()
    for media in re.finditer(r"@media[^{]*max-width[^{]*\{(.*?)\n\}", source, re.S):
        for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", media.group(1)):
            if "grid-template-columns: 1fr" in body:
                classes.update(re.findall(r"\.([\w-]+)", selector))
    return classes


@pytest.mark.parametrize("path", _template_files(), ids=lambda p: p.name)
def test_fixed_width_grids_collapse_on_mobile(path):
    """A sidebar column measured in pixels must fold away on a phone.

    ``grid-cols-[minmax(0,1fr)_300px]`` keeps the sidebar at its full width
    whatever the viewport, so on a 320px screen the main column is squeezed
    to a sliver and the row overflows sideways. The layout only survives
    because a companion class — ``.detail-grid``, ``.editor-grid`` and
    friends — is matched by a ``max-width`` media query that drops the grid
    to one column. Forget that class and the page renders unusably narrow.
    """
    collapsible = _mobile_collapse_classes()
    assert collapsible, "no single-column media queries found in styles.css"
    for attribute in FIXED_COLUMN_GRID.findall(path.read_text()):
        assert collapsible & set(attribute.split()), (
            f"{path.name} has a pixel-width grid column but none of the "
            f"classes {attribute.split()!r} is collapsed on small screens; "
            f"add one of {sorted(collapsible)}."
        )


def test_the_scan_itself_detects_an_uncollapsed_grid():
    """Guards the check above: a scanner that never fires proves nothing."""
    assert FIXED_COLUMN_GRID.findall('<div class="grid grid-cols-3">') == []
    assert FIXED_COLUMN_GRID.findall(
        '<div class="grid grid-cols-[minmax(0,1fr)_300px] gap-5">'
    ) == ["grid grid-cols-[minmax(0,1fr)_300px] gap-5"]
