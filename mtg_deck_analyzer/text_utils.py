"""Text utilities: slugs and Markdown -> ReportLab Flowables conversion."""

import html
import re

from reportlab.lib.colors import HexColor
from reportlab.platypus import HRFlowable, Paragraph, Spacer

# Matches a Markdown horizontal rule (---, ***, ___).
_HR_RE = re.compile(r"^([-*_])\1{2,}$")


def get_card_slug(name: str) -> str:
    """Creates a filesystem-safe slug from a card name."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def slugify(text: str) -> str:
    """Standard slug for filenames."""
    return get_card_slug(text)


def escape_for_paragraph(text: str) -> str:
    """Escapes text for safe embedding in a ReportLab Paragraph."""
    if not text:
        return ""
    return html.escape(text).replace("\n", "<br/>")


def convert_markdown_inline(text: str) -> str:
    """Converts inline Markdown styles into HTML tags for ReportLab Paragraphs."""
    # Escape HTML tags first to avoid XML parsing errors.
    text = html.escape(text)

    # Replace Markdown bold and italics with HTML tags.
    text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"\*(.*?)\*", r"<i>\1</i>", text)
    text = re.sub(r"_(.*?)_", r"<i>\1</i>", text)
    text = re.sub(r"`(.*?)`", r'<font face="Courier">\1</font>', text)
    return text


def markdown_to_flowables(text: str, styles: dict) -> list:
    """Parses a Markdown string and returns a list of ReportLab Flowables."""
    flowables = []
    paragraphs = text.split("\n\n")

    for p in paragraphs:
        p = p.strip()
        if not p:
            continue

        # Horizontal rule: render as a thin divider line, not literal text.
        if _HR_RE.match(p):
            flowables.append(Spacer(1, 4))
            flowables.append(
                HRFlowable(width="100%", thickness=0.5, color=HexColor("#e2e8f0"))
            )
            flowables.append(Spacer(1, 6))
            continue

        # Headings
        if p.startswith("#"):
            level = 0
            while p.startswith("#"):
                level += 1
                p = p[1:]
            p = p.strip()

            if level == 1:
                style_name = "Heading1"
            elif level == 2:
                style_name = "Heading2"
            else:
                style_name = "Heading3"

            flowables.append(Paragraph(convert_markdown_inline(p), styles[style_name]))
            flowables.append(Spacer(1, 6))

        # Lists
        elif p.startswith("- ") or p.startswith("* ") or p.startswith("1. "):
            lines = p.split("\n")
            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # Pick the prefix based on formatting.
                if line.startswith("- ") or line.startswith("* "):
                    prefix = "&bull; "
                    line_text = line[2:]
                elif len(line) > 2 and line[0].isdigit() and ". " in line[:4]:
                    dot_idx = line.find(".")
                    num_str = line[: dot_idx + 1]
                    prefix = f"{num_str} "
                    line_text = line[dot_idx + 1 :].strip()
                else:
                    prefix = "&bull; "
                    line_text = line

                bullet_style = styles["Bullet"]
                flowables.append(
                    Paragraph(f"{prefix}{convert_markdown_inline(line_text)}", bullet_style)
                )
            flowables.append(Spacer(1, 6))

        # Standard paragraph
        else:
            # Join single line breaks that are not double newlines.
            p_text = p.replace("\n", " ")
            flowables.append(Paragraph(convert_markdown_inline(p_text), styles["Normal"]))
            flowables.append(Spacer(1, 8))

    return flowables
