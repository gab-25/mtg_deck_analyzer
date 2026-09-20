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
