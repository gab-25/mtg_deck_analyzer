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


def localize_card_names(text: str, name_map: dict) -> str:
    """Replaces English card names in the analysis text with localized names.

    ``name_map`` maps each English card name (exactly as fed to the analysis
    model) to its localized printed name. The substitution runs in a single pass
    using a combined, case-insensitive pattern; longer names are tried first so a
    card whose name is a prefix of another (e.g. "Tatyova" inside "Tatyova,
    Benthic Druid") is never partially replaced. Word boundaries keep names from
    matching inside larger words. Bold/italic markers around a name are
    preserved, since only the name text itself is rewritten.
    """
    if not text or not name_map:
        return text

    # Skip entries with no real translation (e.g. names identical in both langs).
    pairs = [
        (eng, loc)
        for eng, loc in name_map.items()
        if eng and loc and eng.lower() != loc.lower()
    ]
    if not pairs:
        return text

    # Longest first so the alternation prefers the most specific card name.
    pairs.sort(key=lambda kv: len(kv[0]), reverse=True)
    lookup = {eng.lower(): loc for eng, loc in pairs}
    alternation = "|".join(re.escape(eng) for eng, _ in pairs)
    pattern = re.compile(r"(?<!\w)(" + alternation + r")(?!\w)", re.IGNORECASE)

    return pattern.sub(lambda m: lookup[m.group(1).lower()], text)


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

        # Headings. Only the first line is the heading; any text that follows on
        # the next line(s) is body copy that must not inherit the heading size.
        if p.startswith("#"):
            heading_line, _, remainder = p.partition("\n")

            level = 0
            while heading_line.startswith("#"):
                level += 1
                heading_line = heading_line[1:]
            heading_line = heading_line.strip()

            if level == 1:
                style_name = "Heading1"
            elif level == 2:
                style_name = "Heading2"
            else:
                style_name = "Heading3"

            flowables.append(
                Paragraph(convert_markdown_inline(heading_line), styles[style_name])
            )
            flowables.append(Spacer(1, 6))

            # Process any text following the heading as its own block(s).
            remainder = remainder.strip()
            if remainder:
                flowables.extend(markdown_to_flowables(remainder, styles))

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
