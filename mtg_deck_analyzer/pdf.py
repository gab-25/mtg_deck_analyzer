"""Deck reference PDF generation using ReportLab Platypus."""

import datetime
import html

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    Image as RLImage,
)
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .cards import classify_card, infer_deck_type
from .constants import CATEGORY_ORDER
from .text_utils import markdown_to_flowables

# PDF labels are always English; only the card title and description follow the
# requested language (those come from the Scryfall card data).
_CATEGORY_LABELS = {
    "Creature": "Creatures",
    "Land": "Lands",
    "Planeswalker": "Planeswalkers",
    "Instant": "Instants",
    "Sorcery": "Sorceries",
    "Artifact": "Artifacts",
    "Enchantment": "Enchantments",
    "Battle": "Battles",
    "Other": "Other",
}

_STATS_LABELS = {
    "title": "Deck Fact Sheet",
    "type": "Deck Type",
    "cards": "Total Cards",
    "value": "Estimated Value (Cardmarket)",
    "cmc": "Average CMC (non-Lands)",
}


def create_no_image_placeholder(width=110, height=154):
    """Creates a styled ReportLab Table as a placeholder for missing images."""
    text = "No Image<br/>Available"
    if width < 90:
        text = "No Image"

    no_image_style = ParagraphStyle(
        "PlaceholderStyle",
        fontName="Helvetica",
        fontSize=8,
        alignment=1,  # Center
        textColor=HexColor("#718096"),
        leading=10,
    )

    placeholder = Table(
        [[Paragraph(text, no_image_style)]], colWidths=[width], rowHeights=[height]
    )
    placeholder.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), HexColor("#edf2f7")),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOX", (0, 0), (-1, -1), 0.5, HexColor("#cbd5e0")),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    return placeholder


def create_stats_table(
    total_cards: int,
    total_price: float,
    avg_cmc: float,
    category_counts: dict,
    deck_type: str = None,
):
    """Creates a styled statistics table for the top of the PDF."""
    stats_labels = _STATS_LABELS
    cat_labels = _CATEGORY_LABELS

    primary_color = HexColor("#1a2b4c")
    charcoal_color = HexColor("#2d3748")

    header_style = ParagraphStyle(
        "StatsHeader",
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13,
        textColor=primary_color,
    )

    text_style = ParagraphStyle(
        "StatsText",
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=charcoal_color,
    )

    # Left column: general info.
    val_str = f"€{total_price:.2f}" if total_price > 0.0 else "--"
    type_html = ""
    if deck_type:
        type_html = f'<b>{stats_labels["type"]}:</b> {html.escape(deck_type)}<br/>'
    left_html = f"""
    {type_html}
    <b>{stats_labels["cards"]}:</b> {total_cards}<br/>
    <b>{stats_labels["value"]}:</b> {val_str}<br/>
    <b>{stats_labels["cmc"]}:</b> {avg_cmc:.2f}
    """

    # Right column: per-type counts.
    type_lines = []
    for cat in CATEGORY_ORDER:
        count = category_counts.get(cat, 0)
        if count > 0:
            type_lines.append(f"<b>{cat_labels[cat]}:</b> {count}")

    # Group items in chunks of 3 separated by bullets.
    right_html_lines = []
    chunk_size = 3
    for i in range(0, len(type_lines), chunk_size):
        chunk = type_lines[i : i + chunk_size]
        right_html_lines.append(" &nbsp;&nbsp;&bull;&nbsp;&nbsp; ".join(chunk))

    right_html = "<br/>".join(right_html_lines)

    data = [
        [Paragraph(f"<b>{stats_labels['title']}</b>", header_style), ""],
        [Paragraph(left_html, text_style), Paragraph(right_html, text_style)],
    ]

    stats_table = Table(data, colWidths=[200, 323])
    stats_table.setStyle(
        TableStyle(
            [
                ("SPAN", (0, 0), (1, 0)),  # Span the header
                ("BACKGROUND", (0, 0), (-1, -1), HexColor("#f7fafc")),
                ("BOX", (0, 0), (-1, -1), 1, HexColor("#e2e8f0")),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (1, 0), 0.5, HexColor("#e2e8f0")),
            ]
        )
    )

    return stats_table


def _build_styles():
    """Builds and returns the dictionary of styles used in the PDF."""
    styles = getSampleStyleSheet()

    primary_color = HexColor("#1a2b4c")  # Deep midnight blue
    secondary_color = HexColor("#4a5568")  # Muted slate gray
    charcoal_color = HexColor("#2d3748")  # Dark text

    return {
        "primary": primary_color,
        "secondary": secondary_color,
        "charcoal": charcoal_color,
        "border": HexColor("#e2e8f0"),
        "title": ParagraphStyle(
            "DocTitle",
            parent=styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=25,
            textColor=primary_color,
            spaceAfter=2,
        ),
        "subtitle": ParagraphStyle(
            "DocSubtitle",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=secondary_color,
            spaceAfter=10,
        ),
        # Section heading (## and the "Deck Strategy & Analysis" title).
        "h2": ParagraphStyle(
            "Heading2_Custom",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12.5,
            leading=15,
            textColor=primary_color,
            spaceBefore=10,
            spaceAfter=4,
            keepWithNext=True,
        ),
        # Analysis section heading (the ## headings inside the AI analysis).
        # Deliberately smaller than the "Deck Strategy & Analysis" title (h2) so
        # the section title stays dominant and the inner text reads as content.
        "analysis_heading": ParagraphStyle(
            "AnalysisHeading",
            parent=styles["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=primary_color,
            spaceBefore=9,
            spaceAfter=3,
            keepWithNext=True,
        ),
        # Subsection heading (###, e.g. Early / Mid / Late game).
        "h3": ParagraphStyle(
            "Heading3_Custom",
            parent=styles["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=13,
            textColor=secondary_color,
            spaceBefore=5,
            spaceAfter=2,
            keepWithNext=True,
        ),
        "category_header": ParagraphStyle(
            "CategoryHeader",
            parent=styles["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=primary_color,
            spaceBefore=8,
            spaceAfter=3,
            keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "Body_Custom",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13,
            textColor=charcoal_color,
            spaceAfter=3,
            alignment=4,  # Justified for an even, polished text block.
        ),
        "bullet": ParagraphStyle(
            "Bullet_Custom",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13,
            textColor=charcoal_color,
            leftIndent=14,
            firstLineIndent=-9,
            spaceAfter=2,
        ),
        "card_title": ParagraphStyle(
            "CardTitle",
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=primary_color,
        ),
        "card_type": ParagraphStyle(
            "CardType",
            fontName="Helvetica-Oblique",
            fontSize=8.5,
            leading=11,
            textColor=secondary_color,
        ),
        "card_text": ParagraphStyle(
            "CardText",
            fontName="Helvetica",
            fontSize=8.5,
            leading=11.5,
            textColor=charcoal_color,
        ),
    }


def _compute_statistics(processed_cards: list):
    """Computes aggregate deck statistics (totals, price, average CMC, counts)."""
    total_cards = 0
    total_price = 0.0
    total_non_land_cards = 0
    total_non_land_cmc = 0.0

    category_counts = {cat: 0 for cat in CATEGORY_ORDER}

    for item in processed_cards:
        qty = item["quantity"]
        card = item["data"]
        cat = classify_card(card)
        category_counts[cat] = category_counts.get(cat, 0) + qty

        total_cards += qty
        total_price += qty * card.get("price_eur", 0.0)

        if cat != "Land":
            total_non_land_cards += qty
            total_non_land_cmc += qty * card.get("cmc", 0.0)

    avg_cmc = (
        (total_non_land_cmc / total_non_land_cards) if total_non_land_cards > 0 else 0.0
    )

    return total_cards, total_price, avg_cmc, category_counts


def _build_card_image_cell(image_paths: list, single=(110, 154), face=(80, 112)):
    """Builds the left cell (image/s) of a card row.

    `single` is the (width, height) for a single image; `face` is the size used
    for each side of a double-faced card.
    """
    sw, sh = single
    fw, fh = face

    if len(image_paths) == 1:
        try:
            return RLImage(image_paths[0], width=sw, height=sh)
        except Exception:
            return create_no_image_placeholder(sw, sh)

    if len(image_paths) >= 2:
        face_flowables = []
        for img_path in image_paths[:2]:
            try:
                face_flowables.append(RLImage(img_path, width=fw, height=fh))
            except Exception:
                face_flowables.append(create_no_image_placeholder(fw, fh))
        while len(face_flowables) < 2:
            face_flowables.append(create_no_image_placeholder(fw, fh))

        sub_table = Table([face_flowables], colWidths=[fw + 5, fw + 5])
        sub_table.setStyle(
            TableStyle(
                [
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        return sub_table

    return create_no_image_placeholder(sw, sh)


def _build_card_details_cell(card: dict, qty: int, price: float, styles: dict):
    """Builds the right cell (text details) of a card row."""
    right_cell_flowables = []
    faces = card.get("faces", [])

    for idx, face in enumerate(faces):
        if idx > 0:
            right_cell_flowables.append(Spacer(1, 8))
            divider_label = "// Other Face //"
            divider_style = ParagraphStyle(
                "Divider",
                fontName="Helvetica-Bold",
                fontSize=8,
                textColor=styles["secondary"],
            )
            right_cell_flowables.append(Paragraph(divider_label, divider_style))
            right_cell_flowables.append(Spacer(1, 6))

        escaped_face_name = html.escape(face.get("name", ""))
        escaped_face_cost = html.escape(face.get("mana_cost", ""))

        # Title line (quantity only on the first face).
        if idx == 0:
            title_html = f"<b>{qty}x {escaped_face_name}</b>"
        else:
            title_html = f"<b>{escaped_face_name}</b>"

        if escaped_face_cost:
            title_html += f" &nbsp;&nbsp;&nbsp; <font color='#4a5568'><b>{escaped_face_cost}</b></font>"

        # Add the price if available and we are on the first face.
        if idx == 0 and price > 0.0:
            if qty > 1:
                title_html += (
                    f" &nbsp;&nbsp;&nbsp; <font color='#718096'>€{price:.2f} "
                    f"<font size='7.5' color='#a0aec0'>(€{price * qty:.2f} tot)</font></font>"
                )
            else:
                title_html += (
                    f" &nbsp;&nbsp;&nbsp; <font color='#718096'>€{price:.2f}</font>"
                )

        right_cell_flowables.append(Paragraph(title_html, styles["card_title"]))
        right_cell_flowables.append(Spacer(1, 2))

        # Type line.
        escaped_face_type = html.escape(face.get("type_line", ""))
        if escaped_face_type:
            right_cell_flowables.append(
                Paragraph(f"<i>{escaped_face_type}</i>", styles["card_type"])
            )
            right_cell_flowables.append(Spacer(1, 4))

        # Rules text.
        escaped_face_text = html.escape(face.get("rules_text", "")).replace(
            "\n", "<br/>"
        )
        if escaped_face_text:
            right_cell_flowables.append(
                Paragraph(escaped_face_text, styles["card_text"])
            )

    return right_cell_flowables


# Grid layout: cards are laid out in 2 columns and flow continuously to pack
# pages as densely as possible.
_GRID_COLS = 2
# Half-page card cell: smaller image + details side by side.
_GRID_COL_WIDTH = 261
# Padding between the grid lines and the cell content (so text never touches
# the borders).
_GRID_CELL_PAD_X = 9
_GRID_CELL_PAD_Y = 9
# Inner card content width, once the grid cell padding is removed.
_CARD_INNER_WIDTH = _GRID_COL_WIDTH - 2 * _GRID_CELL_PAD_X
_GRID_IMAGE_WIDTH = 80
_GRID_IMAGE_SINGLE = (_GRID_IMAGE_WIDTH, 112)
_GRID_IMAGE_FACE = (38, 53)


def _build_card_cell(item: dict, styles: dict):
    """Builds one card (image + details) sized to fit half the page width."""
    qty = item["quantity"]
    card = item["data"]
    image_paths = card.get("image_paths", [])
    price = card.get("price_eur", 0.0)

    image = _build_card_image_cell(
        image_paths, single=_GRID_IMAGE_SINGLE, face=_GRID_IMAGE_FACE
    )
    details = _build_card_details_cell(card, qty, price, styles)

    # Image column slightly wider than the image to keep it off the divider;
    # the details column takes the rest of the inner width.
    image_col = _GRID_IMAGE_WIDTH + 6
    cell = Table([[image, details]], colWidths=[image_col, _CARD_INNER_WIDTH - image_col])
    cell.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (0, 0), (0, 0), "CENTER"),
                ("LEFTPADDING", (0, 0), (0, 0), 0),
                ("RIGHTPADDING", (0, 0), (0, 0), 0),
                # Gap between the image and the text block.
                ("LEFTPADDING", (1, 0), (1, 0), 6),
                ("RIGHTPADDING", (1, 0), (1, 0), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return cell


def _make_card_rows_table(rows: list, styles: dict):
    """Builds a 2-column table of card rows with the standard boxed styling."""
    table = Table(rows, colWidths=[_GRID_COL_WIDTH, _GRID_COL_WIDTH])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (1, -1), _GRID_CELL_PAD_X),
                ("RIGHTPADDING", (0, 0), (1, -1), _GRID_CELL_PAD_X),
                ("TOPPADDING", (0, 0), (1, -1), _GRID_CELL_PAD_Y),
                ("BOTTOMPADDING", (0, 0), (1, -1), _GRID_CELL_PAD_Y),
                ("BOX", (0, 0), (1, -1), 0.5, styles["border"]),
                # Divider between the two cards on a row.
                ("LINEAFTER", (0, 0), (0, -1), 0.5, styles["border"]),
            ]
        )
    )
    return table


def _build_card_list_flowables(grouped_cards: dict, styles: dict):
    """Builds the card-list section as a list of flowables.

    Each category is rendered as a header followed by 2-column rows of cards. The
    header is kept together with the first row of cards (via ``KeepTogether``) so
    a category header is never stranded alone at the bottom of a page. The
    remaining rows flow normally and abut the first row seamlessly, so pages
    still fill up and the page count stays minimal.
    """
    flowables = []

    for cat in CATEGORY_ORDER:
        cards_in_cat = grouped_cards[cat]
        if not cards_in_cat:
            continue

        cat_total_qty = sum(item["quantity"] for item in cards_in_cat)
        header = Paragraph(
            f"{_CATEGORY_LABELS[cat]} ({cat_total_qty})", styles["category_header"]
        )

        cells = [_build_card_cell(item, styles) for item in cards_in_cat]
        rows = []
        for i in range(0, len(cells), _GRID_COLS):
            pair = cells[i : i + _GRID_COLS]
            while len(pair) < _GRID_COLS:
                pair.append("")  # filler so the row has 2 columns
            rows.append(pair)

        # Glue the header to the first row of cards.
        flowables.append(KeepTogether([header, _make_card_rows_table(rows[:1], styles)]))
        # Remaining rows flow (and may split across pages) right below.
        if len(rows) > 1:
            flowables.append(_make_card_rows_table(rows[1:], styles))

    return flowables


def generate_pdf(
    deck_name: str,
    deck_analysis: str,
    processed_cards: list,
    output_path: str,
):
    """Generates the formatted PDF using the ReportLab Platypus layout."""
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=40,
        bottomMargin=40,
    )
    doc.deck_name = deck_name

    styles = _build_styles()
    story_flowables = []

    # 1. Deck header.
    story_flowables.append(Paragraph(deck_name, styles["title"]))

    today_str = datetime.date.today().strftime("%Y-%m-%d")

    subtitle_text = f"Magic: The Gathering Deck List &bull; Generated on: {today_str}"
    story_flowables.append(Paragraph(subtitle_text, styles["subtitle"]))

    # 1.1 Statistics and summary table.
    total_cards, total_price, avg_cmc, category_counts = _compute_statistics(
        processed_cards
    )
    deck_type = infer_deck_type(processed_cards)
    stats_table = create_stats_table(
        total_cards, total_price, avg_cmc, category_counts, deck_type
    )
    story_flowables.append(stats_table)
    story_flowables.append(Spacer(1, 6))

    # 2. Gemini analysis section.
    if deck_analysis:
        story_flowables.append(Paragraph("Deck Strategy & Analysis", styles["h2"]))

        markdown_styles = {
            "Normal": styles["body"],
            "Heading1": styles["analysis_heading"],
            "Heading2": styles["analysis_heading"],
            "Heading3": styles["h3"],
            "Bullet": styles["bullet"],
        }

        story_flowables.extend(markdown_to_flowables(deck_analysis, markdown_styles))
        story_flowables.append(Spacer(1, 8))

    # 3. Card list: a single continuous 2-column table so pages fill up and the
    # page count stays minimal.
    story_flowables.append(Paragraph("Card List", styles["h2"]))
    story_flowables.append(Spacer(1, 2))

    grouped_cards = {cat: [] for cat in CATEGORY_ORDER}
    for item in processed_cards:
        cat = classify_card(item["data"])
        grouped_cards[cat].append(item)

    story_flowables.extend(_build_card_list_flowables(grouped_cards, styles))

    doc.build(
        story_flowables,
        onFirstPage=_add_page_decorations,
        onLaterPages=_add_page_decorations,
    )


def _add_page_decorations(canvas, doc):
    """Callback for the header, footer, and page numbering."""
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(HexColor("#718096"))

    # Footer.
    canvas.drawString(36, 20, f"MTG Deck Analyzer - {doc.deck_name}")
    canvas.drawRightString(doc.pagesize[0] - 36, 20, f"Page {doc.page}")

    # Header (from page 2 onward).
    if doc.page > 1:
        canvas.drawString(36, doc.pagesize[1] - 25, doc.deck_name)
        canvas.setStrokeColor(HexColor("#e2e8f0"))
        canvas.setLineWidth(0.5)
        canvas.line(
            36, doc.pagesize[1] - 30, doc.pagesize[0] - 36, doc.pagesize[1] - 30
        )

    canvas.restoreState()
