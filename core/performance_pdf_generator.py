"""
performance_pdf_generator.py
-----------------------------
Premium landscape A4 PDF report generator for the Nasmat 3PL Rider
Performance report.

Layout per page:
  ┌──────────────────────────────────────────────────────────────────────────────┐
  │  [Logo]  شركة نسمات الشرق        Nasmat Al-Sharq                            │
  │          للخدمات اللوجستية       Logistics Services Co.                      │
  │  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━   │
  │   3PL Rider Performance Report  ·  Aug 2026  ·  Generated: 17/08/2026        │
  ├──────────────────────────────────────────────────────────────────────────────┤
  │ SR │ RIDER ID │   NAME   │ COMP.DEL│SHF│PLN HRS│ACT HRS│ATTEND│BRK│LST│ACC│
  │────┼──────────┼──────────┼─────────┼───┼───────┼───────┼──────┼───┼───┼───│
  │ 1  │ 783304   │ محمد …   │   32    │ 6 │ 16.00 │ 18.27 │ 100% │ - │0.72│100%│
  │ …                                                                            │
  ├──────────────────────────────────────────────────────────────────────────────┤
  │  Nasmat Al-Sharq Logistics Services Co.  ·  Confidential          Page 1    │
  └──────────────────────────────────────────────────────────────────────────────┘

Orientation : Landscape A4  (841.89 × 595.28 pt  →  usable ≈ 785 pt wide)
Column total: 277 mm  (10+20+63+22+14+21+21+22+18+16+22+28)
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
from reportlab.lib.pagesizes import A4, landscape
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
from models.schemas import PerformanceRow

logger = logging.getLogger(__name__)

# ── Page geometry ──────────────────────────────────────────────────────────────
PAGE_SIZE = landscape(A4)          # 841.89 × 595.28 pt

BASE_DIR  = Path(__file__).parent.parent
FONT_PATH = BASE_DIR / "fonts" / "Amiri-Regular.ttf"

# ── Palette ────────────────────────────────────────────────────────────────────
_LIGHT = colors.HexColor("#EBF8F8")   # alternating row tint
_GRAY  = colors.HexColor("#6B7280")   # muted gray — subtitle, footer

_WHITE = colors.white

# Attendance / Acceptance rate colour bands
_GREEN_BG = colors.HexColor("#D1FAE5")
_AMBER_BG = colors.HexColor("#FEF3C7")
_RED_BG   = colors.HexColor("#FEE2E2")
_GREEN_FG = colors.HexColor("#065F46")
_AMBER_FG = colors.HexColor("#92400E")
_RED_FG   = colors.HexColor("#991B1B")

_FONT_REGISTERED = False


# ── Helpers ────────────────────────────────────────────────────────────────────

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
    """Reshape + BiDi-apply Arabic text for correct right-to-left PDF rendering."""
    if not text:
        return text
    return get_display(arabic_reshaper.reshape(text))


def _fmt_hours(val: float) -> str:
    """Return '-' for zero, otherwise 2-decimal-place string."""
    if val == 0.0:
        return "-"
    return f"{val:.2f}"


def _attendance_colors(pct: int) -> tuple[colors.Color, colors.Color]:
    """Return (bg, fg) colour pair for an attendance percentage."""
    if pct >= 95:
        return _GREEN_BG, _GREEN_FG
    if pct >= 80:
        return _AMBER_BG, _AMBER_FG
    return _RED_BG, _RED_FG


def _acceptance_colors(pct: int) -> tuple[colors.Color, colors.Color]:
    """Return (bg, fg) colour pair for an acceptance percentage."""
    if pct >= 100:
        return _GREEN_BG, _GREEN_FG
    if pct >= 90:
        return _AMBER_BG, _AMBER_FG
    return _RED_BG, _RED_FG


# ── Footer callback ────────────────────────────────────────────────────────────

def _make_perf_footer(canvas, doc) -> None:
    """Draw teal rule + company branding + page number on every page."""
    canvas.saveState()

    page_w  = PAGE_SIZE[0]           # landscape width
    left_m  = 10 * mm
    right_m = page_w - 10 * mm

    # Teal rule
    canvas.setStrokeColor(BRAND_TEAL)
    canvas.setLineWidth(0.7)
    canvas.line(left_m, 14 * mm, right_m, 14 * mm)

    # Company + page number
    canvas.setFont("Helvetica", 6.5)
    canvas.setFillColor(_GRAY)
    canvas.drawString(
        left_m, 9 * mm,
        "Nasmat Al-Sharq Logistics Services Co.  ·  Confidential",
    )
    canvas.drawRightString(
        right_m, 9 * mm,
        f"Page {canvas.getPageNumber()}",
    )

    canvas.restoreState()


# ── Public API ─────────────────────────────────────────────────────────────────

def generate_performance_pdf(
    rows: list[PerformanceRow],
    report_date: str | None = None,
) -> bytes:
    """
    Build and return the Rider Performance PDF as bytes.

    Args:
        rows:         Ordered list of PerformanceRow (caller responsible for sorting).
        report_date:  Month/year label, e.g. "Aug 2026".  Auto-generated if None.

    Returns:
        PDF content as bytes.

    Raises:
        FileNotFoundError: if the Amiri font is missing.
        RuntimeError:      if the output PDF is suspiciously small.
    """
    _ensure_font()

    buf        = io.BytesIO()
    rpt_date   = report_date or datetime.now().strftime("%b %Y")
    generated  = datetime.now().strftime("%d/%m/%Y")

    doc = SimpleDocTemplate(
        buf,
        pagesize=PAGE_SIZE,
        leftMargin=10 * mm,
        rightMargin=10 * mm,
        topMargin=8 * mm,
        bottomMargin=22 * mm,          # space reserved for footer
        title="3PL Rider Performance Report — Nasmat Al-Sharq",
        author="Nasmat Al-Sharq Logistics Services Co.",
    )

    story: list = []
    usable_w = PAGE_SIZE[0] - 20 * mm   # ≈ 785 pt  (landscape A4 = 841.89pt)

    # ── SECTION 1: Company Header ─────────────────────────────────────────────

    logo = create_logo_drawing(width=55, height=50)

    _s_ar_main = ParagraphStyle(
        "PArMain",
        fontName="Amiri", fontSize=15,
        alignment=TA_RIGHT, leading=20,
        textColor=BRAND_TEAL, spaceAfter=1,
    )
    _s_ar_sub = ParagraphStyle(
        "PArSub",
        fontName="Amiri", fontSize=9.5,
        alignment=TA_RIGHT, leading=13,
        textColor=BRAND_DARK,
    )
    _s_en_name = ParagraphStyle(
        "PEnName",
        fontName="Helvetica-Bold", fontSize=8,
        alignment=TA_RIGHT, leading=11,
        textColor=BRAND_DARK, spaceBefore=4,
    )
    _s_en_sub = ParagraphStyle(
        "PEnSub",
        fontName="Helvetica", fontSize=7,
        alignment=TA_RIGHT, leading=9,
        textColor=_GRAY,
    )

    name_block = [
        Paragraph(_ar("شركة نسمات الشرق"),  _s_ar_main),
        Paragraph(_ar("للخدمات اللوجستية"), _s_ar_sub),
        Paragraph("Nasmat Al-Sharq",          _s_en_name),
        Paragraph("Logistics Services Co.",   _s_en_sub),
    ]

    logo_col_w = 62
    name_col_w = usable_w - logo_col_w

    header_tbl = Table([[logo, name_block]], colWidths=[logo_col_w, name_col_w])
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
    divider = Table([[""]], colWidths=[usable_w], rowHeights=[3])
    divider.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), BRAND_TEAL),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
    ]))
    story.append(divider)

    # ── Report subtitle ───────────────────────────────────────────────────────
    _s_subtitle = ParagraphStyle(
        "PSubtitle",
        fontName="Helvetica", fontSize=7.5,
        alignment=TA_CENTER, textColor=_GRAY,
        spaceBefore=5, spaceAfter=9,
    )
    story.append(Paragraph(
        f"3PL Rider Performance Report  ·  {rpt_date}  ·  Generated: {generated}",
        _s_subtitle,
    ))

    # ── SECTION 2: Data Table ─────────────────────────────────────────────────
    # 12 columns, total 277 mm = usable landscape width
    col_widths = [
        10 * mm,   # SR
        20 * mm,   # Rider ID
        63 * mm,   # Name (Arabic — needs generous space)
        22 * mm,   # Completed Deliveries
        14 * mm,   # # Shifts
        21 * mm,   # Planned Hours
        21 * mm,   # Actual Hours
        22 * mm,   # Attendance Rate  ← colour-coded
        18 * mm,   # Break Hours
        16 * mm,   # Lost Hours
        22 * mm,   # Acceptance Rate  ← colour-coded
        28 * mm,   # Declined Deliveries
    ]

    _s_th = ParagraphStyle(
        "PTH",
        fontName="Amiri", fontSize=6.5,
        alignment=TA_CENTER, leading=8, textColor=_WHITE,
    )
    _s_td_c = ParagraphStyle(
        "PTDC",
        fontName="Amiri", fontSize=8,
        alignment=TA_CENTER, leading=10,
    )
    _s_td_n = ParagraphStyle(
        "PTDN",
        fontName="Amiri", fontSize=8.5,
        alignment=TA_RIGHT, leading=10,
    )

    # ── Header row ────────────────────────────────────────────────────────────
    table_data: list[list] = [[
        Paragraph("SR",                    _s_th),
        Paragraph("RIDER ID",              _s_th),
        Paragraph("NAME",                  _s_th),
        Paragraph("COMPLETED\nDELIVERIES", _s_th),
        Paragraph("SHIFTS",                _s_th),
        Paragraph("PLANNED\nHRS",          _s_th),
        Paragraph("ACTUAL\nHRS",           _s_th),
        Paragraph("ATTENDANCE\nRATE",      _s_th),
        Paragraph("BREAK\nHRS",            _s_th),
        Paragraph("LOST\nHRS",             _s_th),
        Paragraph("ACCEPTANCE\nRATE",      _s_th),
        Paragraph("DECLINED\nDELIVERIES",  _s_th),
    ]]

    # ── Data rows ─────────────────────────────────────────────────────────────
    for i, row in enumerate(rows):
        att_bg, att_fg = _attendance_colors(row.attendance_rate)
        acc_bg, acc_fg = _acceptance_colors(row.acceptance_rate)

        _s_att = ParagraphStyle(
            f"PAtt{i}",
            fontName="Amiri", fontSize=8,
            alignment=TA_CENTER, leading=10, textColor=att_fg,
        )
        _s_acc = ParagraphStyle(
            f"PAcc{i}",
            fontName="Amiri", fontSize=8,
            alignment=TA_CENTER, leading=10, textColor=acc_fg,
        )

        table_data.append([
            Paragraph(str(i + 1),                          _s_td_c),
            Paragraph(row.rider_id,                        _s_td_c),
            Paragraph(_ar(row.name),                       _s_td_n),
            Paragraph(str(row.completed_deliveries),        _s_td_c),
            Paragraph(str(row.shifts),                     _s_td_c),
            Paragraph(f"{row.planned_hours:.2f}",          _s_td_c),
            Paragraph(f"{row.actual_hours:.2f}",           _s_td_c),
            Paragraph(f"{row.attendance_rate}%",           _s_att),
            Paragraph(_fmt_hours(row.break_hours),         _s_td_c),
            Paragraph(_fmt_hours(row.lost_hours),          _s_td_c),
            Paragraph(f"{row.acceptance_rate}%",           _s_acc),
            Paragraph(str(row.declined_deliveries),        _s_td_c),
        ])

    tbl = Table(table_data, colWidths=col_widths, repeatRows=1)

    # ── Base table style ──────────────────────────────────────────────────────
    ts_cmds = [
        # Header row
        ("BACKGROUND",    (0, 0), (-1, 0),  BRAND_DARK),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  _WHITE),
        ("LINEBELOW",     (0, 0), (-1, 0),  1.5, BRAND_TEAL),

        # All cells
        ("FONTNAME",      (0, 0), (-1, -1), "Amiri"),
        ("FONTSIZE",      (0, 1), (-1, -1), 8),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 3),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 3),

        # Grid
        ("GRID",          (0, 0), (-1, -1), 0.3, colors.HexColor("#D1D5DB")),

        # Name column: right-aligned
        ("ALIGN",         (2, 1), (2, -1),  "RIGHT"),

        # Teal left-edge accent
        ("LINEBEFORE",    (0, 0), (0, -1),  2.5, BRAND_TEAL),
    ]

    # ── Per-row: alternating background + rate column colours ─────────────────
    ATT_COL = 7    # Attendance Rate column index
    ACC_COL = 10   # Acceptance Rate column index

    for i, row in enumerate(rows):
        r      = i + 1                 # table row index (0 = header)
        row_bg = _LIGHT if i % 2 == 0 else _WHITE
        att_bg, _ = _attendance_colors(row.attendance_rate)
        acc_bg, _ = _acceptance_colors(row.acceptance_rate)

        # All columns get alternating background except the rate columns
        for c in range(12):
            if c == ATT_COL:
                ts_cmds.append(("BACKGROUND", (c, r), (c, r), att_bg))
            elif c == ACC_COL:
                ts_cmds.append(("BACKGROUND", (c, r), (c, r), acc_bg))
            else:
                ts_cmds.append(("BACKGROUND", (c, r), (c, r), row_bg))

    tbl.setStyle(TableStyle(ts_cmds))
    story.append(tbl)
    story.append(Spacer(1, 4 * mm))

    # ── Build ──────────────────────────────────────────────────────────────────
    doc.build(story, onFirstPage=_make_perf_footer, onLaterPages=_make_perf_footer)

    pdf_bytes = buf.getvalue()
    if len(pdf_bytes) < 1000:
        raise RuntimeError(
            "Generated Performance PDF is suspiciously small — possible rendering error."
        )

    logger.info(
        "Performance PDF generated: %d bytes, %d rows", len(pdf_bytes), len(rows)
    )
    return pdf_bytes
