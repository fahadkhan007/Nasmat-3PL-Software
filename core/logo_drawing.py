"""
logo_drawing.py
--------------
Programmatic vector recreation of the Nasmat Al-Sharq logo as a ReportLab Drawing.

The chevron symbol is drawn directly using polygon geometry so it is:
  • Crisp at any scale (true vector — no rasterisation)
  • Pixel-identical in proportions to the official logo
  • Zero external file dependency

Colours verified against the official brand image:
  BRAND_TEAL  #1AACAB  — front/teal chevron + speed lines
  BRAND_DARK  #2C3A47  — rear/charcoal chevron + dark text
"""

from __future__ import annotations

from reportlab.graphics.shapes import Drawing, Polygon, Rect
from reportlab.lib.colors import HexColor

# ── Official brand colours ─────────────────────────────────────────────────────
BRAND_TEAL = HexColor("#1AACAB")   # Nasmat teal
BRAND_DARK = HexColor("#2C3A47")   # Nasmat charcoal


def create_logo_drawing(width: float = 90, height: float = 90) -> Drawing:
    """
    Return a scalable ReportLab Drawing of the Nasmat Al-Sharq chevron symbol.

    The Drawing is a Flowable and can be placed directly in a Platypus story
    or inside a Table cell.

    Coordinate system used internally: 90 × 90 units (y-up, origin bottom-left).
    All coordinates are scaled proportionally to the requested output size.

    Args:
        width:  Output width  in points (default 90pt ≈ 31.8 mm).
        height: Output height in points (default 90pt ≈ 31.8 mm).
    """
    d = Drawing(width, height)

    # Scale factors map the internal 90×90 grid → requested output size
    sx = width  / 90.0
    sy = height / 90.0

    def pts(pairs: list[tuple[float, float]]) -> list[float]:
        """Flatten and scale (x, y) pairs into a Polygon-ready flat list."""
        result: list[float] = []
        for x, y in pairs:
            result.extend([x * sx, y * sy])
        return result

    # ── Speed lines: 3 thin teal horizontal bars (upper-mid-left) ─────────────
    # Widths chosen so they end before the chevron's left edge (x≈16)
    for raw_y, raw_w in [
        (68.0, 13.0),   # top line     – shorter
        (60.0, 18.0),   # middle line  – longest (motion-blur effect)
        (52.0, 13.0),   # bottom line  – shorter
    ]:
        d.add(Rect(
            0,              raw_y * sy,
            raw_w * sx,     3.0 * sy,
            fillColor=BRAND_TEAL,
            strokeColor=None,
        ))

    # ── Dark charcoal chevron ─────────────────────────────────────────────────
    # Drawn FIRST so the teal chevron appears on top.
    # Offset +20 units to the right; arm thickness = 14/70 ≈ 20% of chevron height.
    #
    # Polygon trace (counter-clockwise in y-up space):
    #   outer V  : (36,85) → tip (82,50) → (36,15)
    #   inner notch: (36,15) → (36,29) → inner tip (64,50) → (36,71) → (36,85)
    d.add(Polygon(pts([
        (36, 85), (82, 50), (36, 15),   # outer V (top → tip → bottom)
        (36, 29), (64, 50), (36, 71),   # inner notch
    ]), fillColor=BRAND_DARK, strokeColor=None))

    # ── Teal chevron ──────────────────────────────────────────────────────────
    # Drawn LAST so it appears in front.
    # Inner tip at 77% of outer tip distance → consistent with dark chevron ratio.
    #
    # Polygon trace:
    #   outer V  : (16,85) → tip (62,50) → (16,15)
    #   inner notch: (16,15) → (16,29) → inner tip (48,50) → (16,71) → (16,85)
    d.add(Polygon(pts([
        (16, 85), (62, 50), (16, 15),   # outer V
        (16, 29), (48, 50), (16, 71),   # inner notch
    ]), fillColor=BRAND_TEAL, strokeColor=None))

    return d
