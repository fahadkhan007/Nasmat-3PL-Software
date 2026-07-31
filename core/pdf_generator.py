"""
pdf_generator.py
----------------
Premium PDF report generator for Nasmat Al-Sharq Logistics.

Layout per page:
  ┌─────────────────────────────────────────────────────────────────┐
  │  [Logo Symbol]   شركة نسمات الشرق        Nasmat Al-Sharq       │
  │                  للخدمات اللوجستية       Logistics Services Co. │
  │  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
  │      3PL Delivery Quality Report  ·  Jul 2026  ·  31/07/2026   │
  ├─────────────────────────────────────────────────────────────────┤
  │  SR │ ID NO │       NAMES        │ ORDERS │ON TIME│PERCENT│ SEG │
  │─────┼───────┼────────────────────┼────────┼───────┼───────┼─────│
  │  1  │  ...  │  مصطفى العبدلي    │   606  │  601  │  100% │  A  │
  │  …  │  …    │  …                 │   …    │  …    │   …   │  …  │
  ├─────────────────────────────────────────────────────────────────┤
  │  Nasmat Al-Sharq Logistics Services Co.  |  Confidential  Pg 1 │
  └─────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import io
import logging
from datetime import datetime
from pathlib import Path

import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from core.logo_drawing import BRAND_DARK, BRAND_TEAL, create_logo_drawing
from models.schemas import ProcessedRow

logger = logging.getLogger(__name__)

BASE_DIR  = Path(__file__).parent.parent
FONT_PATH = BASE_DIR / "fonts" / "Amiri-Regular.ttf"

# ── Derived palette ────────────────────────────────────────────────────────────
_LIGHT = colors.HexColor("#EBF8F8")   # very-light teal tint — alternating rows
_GRAY  = colors.HexColor("#6B7280")   # muted gray — subtitles, footer
_WHITE = colors.white

# ── Segment colour map ─────────────────────────────────────────────────────────
SEGMENT_COLORS: dict[str, tuple[colors.Color, colors.Color]] = {
    # (background,                 text)
    "A": (colors.HexColor("#22C55E"), _WHITE),
    "B": (colors.HexColor("#86EFAC"), colors.HexColor("#14532D")),
    "C": (colors.HexColor("#FCD34D"), colors.HexColor("#78350F")),
    "D": (colors.HexColor("#FB923C"), _WHITE),
    "E": (colors.HexColor("#EF4444"), _WHITE),
    "F": (BRAND_DARK,                 _WHITE),
}

_FONT_REGISTERED = False


def _ensure_font() -> None:
    global _FONT_REGISTERED
    if _FONT_REGISTERED:
        return
    if not FONT_PATH.exists():
        raise FileNotFoundError(f"Arabic font not found: {FONT_PATH}")
    pdfmetrics.registerFont(TTFont("Amiri", str(FONT_PATH)))
    _FONT_REGISTERED = True
    logger.debug("Registered Amiri font: %s", FONT_PATH)


def _ar(text: str) -> str:
    """Reshape + BiDi-apply Arabic for correct right-to-left PDF rendering."""
    if not text:
        return text
    return get_display(arabic_reshaper.reshape(text))


# ── Page footer callback ───────────────────────────────────────────────────────

def _make_footer(canvas, doc) -> None:
    """Draw a teal rule + company branding + page number on every page."""
    canvas.saveState()

    page_w  = A4[0]
    left_m  = 10 * mm
    right_m = page_w - 10 * mm

    # Teal horizontal rule
    canvas.setStrokeColor(BRAND_TEAL)
    canvas.setLineWidth(0.7)
    canvas.line(left_m, 18 * mm, right_m, 18 * mm)

    # Left: company name
    canvas.setFont("Helvetica", 6.5)
    canvas.setFillColor(_GRAY)
    canvas.drawString(
        left_m, 13 * mm,
        "Nasmat Al-Sharq Logistics Services Co.  ·  Confidential",
    )

    # Right: page number
    canvas.drawRightString(
        right_m, 13 * mm,
        f"Page {canvas.getPageNumber()}",
    )

    canvas.restoreState()


# ── Public API ─────────────────────────────────────────────────────────────────

def generate_pdf(rows: list[ProcessedRow], month: str | None = None) -> bytes:
    """
    Build and return the PDF report as bytes.

    Args:
        rows:   Ordered list of ProcessedRow (caller is responsible for sorting).
        month:  Report month label shown in the header/subtitle.

    Returns:
        PDF file content as bytes.

    Raises:
        FileNotFoundError: if the Amiri font is missing.
        RuntimeError:      if the output PDF is suspiciously small.
    """
    _ensure_font()

    buf = io.BytesIO()
    report_month = month or ""
    generated    = datetime.now().strftime("%d/%m/%Y")

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=10 * mm,
        rightMargin=10 * mm,
        topMargin=8 * mm,
        bottomMargin=24 * mm,          # space reserved for footer
        title="3PL Delivery Quality Report — Nasmat Al-Sharq",
        author="Nasmat Al-Sharq Logistics Services Co.",
    )

    story: list = []
    usable_w = A4[0] - 20 * mm        # ≈ 539 pt  (A4 = 595pt, margins 2×10mm)

    # ── SECTION 1: Company Header ─────────────────────────────────────────────

    logo = create_logo_drawing(width=55, height=50)

    # Arabic name styles
    _s_ar_main = ParagraphStyle(
        "ArMain",
        fontName="Amiri", fontSize=15,
        alignment=TA_RIGHT, leading=20,
        textColor=BRAND_TEAL, spaceAfter=1,
    )
    _s_ar_sub = ParagraphStyle(
        "ArSub",
        fontName="Amiri", fontSize=9.5,
        alignment=TA_RIGHT, leading=13,
        textColor=BRAND_DARK,
    )
    # English name styles
    _s_en_name = ParagraphStyle(
        "EnName",
        fontName="Helvetica-Bold", fontSize=8,
        alignment=TA_RIGHT, leading=11,
        textColor=BRAND_DARK, spaceBefore=4,
    )
    _s_en_sub = ParagraphStyle(
        "EnSub",
        fontName="Helvetica", fontSize=7,
        alignment=TA_RIGHT, leading=9,
        textColor=_GRAY,
    )

    name_block = [
        Paragraph(_ar("شركة نسمات الشرق"),          _s_ar_main),
        Paragraph(_ar("للخدمات اللوجستية"),           _s_ar_sub),
        Paragraph("Nasmat Al-Sharq",                   _s_en_name),
        Paragraph("Logistics Services Co.",             _s_en_sub),
    ]

    logo_col_w = 62            # pts — logo cell
    name_col_w = usable_w - logo_col_w

    header_tbl = Table(
        [[logo, name_block]],
        colWidths=[logo_col_w, name_col_w],
    )
    header_tbl.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",         (0, 0), (0,  0),  "LEFT"),
        ("ALIGN",         (1, 0), (1,  0),  "RIGHT"),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
    ]))
    story.append(header_tbl)

    # ── Teal divider band ─────────────────────────────────────────────────────
    divider_tbl = Table(
        [[""]],
        colWidths=[usable_w],
        rowHeights=[3],
    )
    divider_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), BRAND_TEAL),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
    ]))
    story.append(divider_tbl)

    # ── Report subtitle ───────────────────────────────────────────────────────
    _s_subtitle = ParagraphStyle(
        "Subtitle",
        fontName="Helvetica", fontSize=7.5,
        alignment=TA_CENTER, textColor=_GRAY,
        spaceBefore=5, spaceAfter=9,
    )
    story.append(Paragraph(
        f"3PL Delivery Quality Report  ·  {report_month}  ·  Generated: {generated}",
        _s_subtitle,
    ))

    # ── SECTION 2: Data Table ─────────────────────────────────────────────────
    # Column widths — total 175mm = 496pt.
    # With 3pt L+R padding per cell × 7 cols = 42pt → total ≈ 538pt (fits in 539pt).
    col_widths = [
        10 * mm,   #  SR        ≈ 28 pt
        20 * mm,   #  ID NO     ≈ 57 pt
        82 * mm,   #  NAMES     ≈ 232 pt
        17 * mm,   #  ORDERS    ≈ 48 pt
        17 * mm,   #  ON TIME   ≈ 48 pt
        17 * mm,   #  PERCENT   ≈ 48 pt
        12 * mm,   #  SEG       ≈ 34 pt
    ]

    _s_th = ParagraphStyle(
        "TH",
        fontName="Amiri", fontSize=8,
        alignment=TA_CENTER, leading=10, textColor=_WHITE,
    )
    _s_td_c = ParagraphStyle(
        "TDC",
        fontName="Amiri", fontSize=8,
        alignment=TA_CENTER, leading=10,
    )
    _s_td_n = ParagraphStyle(
        "TDN",
        fontName="Amiri", fontSize=8.5,
        alignment=TA_RIGHT, leading=10,
    )

    # Header row
    table_data: list[list] = [[
        Paragraph("SR",       _s_th),
        Paragraph("ID NO",    _s_th),
        Paragraph("NAMES",    _s_th),
        Paragraph("ORDERS",   _s_th),
        Paragraph("ON TIME",  _s_th),
        Paragraph("PERCENT",  _s_th),
        Paragraph("SEG",      _s_th),
    ]]

    # Data rows
    for i, row in enumerate(rows):
        seg_bg, seg_fg = SEGMENT_COLORS.get(row.segment, (_WHITE, colors.black))
        _s_seg = ParagraphStyle(
            f"Seg{i}",
            fontName="Amiri", fontSize=9,
            alignment=TA_CENTER, leading=10,
            textColor=seg_fg,
        )
        table_data.append([
            Paragraph(str(i + 1),         _s_td_c),
            Paragraph(row.rider_id,        _s_td_c),
            Paragraph(_ar(row.name),       _s_td_n),
            Paragraph(str(row.orders),     _s_td_c),
            Paragraph(str(row.on_time),    _s_td_c),
            Paragraph(f"{row.percent}%",   _s_td_c),
            Paragraph(row.segment,         _s_seg),
        ])

    tbl = Table(table_data, colWidths=col_widths, repeatRows=1)

    # Base table style
    ts_cmds = [
        # ── header row ──────────────────────────────────────────────────────
        ("BACKGROUND",    (0, 0), (-1, 0),  BRAND_DARK),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  _WHITE),
        ("LINEBELOW",     (0, 0), (-1, 0),  1.5, BRAND_TEAL),

        # ── all cells ───────────────────────────────────────────────────────
        ("FONTNAME",      (0, 0), (-1, -1), "Amiri"),
        ("FONTSIZE",      (0, 1), (-1, -1), 8),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 3),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 3),

        # ── grid lines ──────────────────────────────────────────────────────
        ("GRID",          (0, 0), (-1, -1), 0.3, colors.HexColor("#D1D5DB")),

        # ── names column: right-aligned ──────────────────────────────────
        ("ALIGN",         (2, 1), (2, -1),  "RIGHT"),

        # ── teal accent: left edge of entire table ───────────────────────
        ("LINEBEFORE",    (0, 0), (0, -1),  2.5, BRAND_TEAL),
    ]

    # Per-row: alternating background + segment cell colour
    for i, row in enumerate(rows):
        r = i + 1                     # table row index (0 = header)
        row_bg = _LIGHT if i % 2 == 0 else _WHITE
        ts_cmds.append(("BACKGROUND", (0, r), (-2, r), row_bg))
        seg_bg, _ = SEGMENT_COLORS.get(row.segment, (_WHITE, colors.black))
        ts_cmds.append(("BACKGROUND", (-1, r), (-1, r), seg_bg))

    tbl.setStyle(TableStyle(ts_cmds))
    story.append(tbl)
    story.append(Spacer(1, 4 * mm))

    # ── Build ──────────────────────────────────────────────────────────────────
    doc.build(story, onFirstPage=_make_footer, onLaterPages=_make_footer)

    pdf_bytes = buf.getvalue()
    if len(pdf_bytes) < 1000:
        raise RuntimeError(
            "Generated PDF is suspiciously small — possible rendering error."
        )

    logger.info("PDF generated: %d bytes, %d rows", len(pdf_bytes), len(rows))
    return pdf_bytes
