"""
csv_processor.py
----------------
Validates, parses, and enriches the daily 3PL CSV.

Strict rules (any violation raises DataError with actionable message):
  - All required columns must be present
  - Scores must be in [0.0, 1.0]
  - Segments must be one of A-F
  - Every rider_id must resolve to a name in the lookup
  - CSV must not be empty
"""

from __future__ import annotations

import io
import logging
from typing import Any

import pandas as pd

from models.schemas import ProcessedRow, RiderPreview

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = {
    "rider_id",
    "completed_orders",
    "completed_orders_in_time",
    "final_delivery_quality_score",
    "segment",
    "city_name",
    "month",
}

VALID_SEGMENTS = {"A", "B", "C", "D", "E", "F"}


class DataError(ValueError):
    """Raised when the CSV fails any integrity check."""


def process_csv(
    content: bytes,
    rider_lookup: dict[str, str],
) -> list[ProcessedRow]:
    """
    Parse raw CSV bytes, validate every field, join rider names, and return
    a sorted list of ProcessedRow ready for PDF generation.

    Args:
        content:       Raw bytes of the uploaded CSV file.
        rider_lookup:  Dict mapping rider_id (str) → name (str).

    Returns:
        List[ProcessedRow] sorted by final_delivery_quality_score descending.

    Raises:
        DataError: On any validation or integrity failure.
    """
    # ── 1. Parse CSV ──────────────────────────────────────────────────────────
    try:
        df = pd.read_csv(io.BytesIO(content), dtype=str)
    except Exception as exc:
        raise DataError(f"Could not parse CSV: {exc}") from exc

    if df.empty:
        raise DataError("The uploaded CSV file is empty.")

    # Normalise column names to lowercase (the real CSV has 'Month' capitalised)
    df.columns = [c.strip().lower() for c in df.columns]

    # ── 2. Column validation ──────────────────────────────────────────────────
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise DataError(
            f"Missing required column(s): {', '.join(sorted(missing))}"
        )

    # ── 3. Strip whitespace ───────────────────────────────────────────────────
    df = df.apply(lambda col: col.map(lambda x: x.strip() if isinstance(x, str) else x))

    # ── 4. Type coercion ──────────────────────────────────────────────────────
    try:
        df["final_delivery_quality_score"] = df[
            "final_delivery_quality_score"
        ].astype(float)
    except ValueError:
        raise DataError("Column 'final_delivery_quality_score' contains non-numeric values.")

    for col in ("completed_orders", "completed_orders_in_time"):
        try:
            df[col] = df[col].astype(int)
        except ValueError:
            raise DataError(f"Column '{col}' must contain whole numbers.")

    # ── 5. Score range validation ─────────────────────────────────────────────
    bad_score = df[
        (df["final_delivery_quality_score"] < 0.0)
        | (df["final_delivery_quality_score"] > 1.0)
    ]
    if not bad_score.empty:
        bad_vals = bad_score["final_delivery_quality_score"].tolist()
        raise DataError(
            f"final_delivery_quality_score out of [0, 1] range at "
            f"row(s) {bad_score.index.tolist()}: {bad_vals}"
        )

    # ── 6. Segment validation ─────────────────────────────────────────────────
    bad_seg = df[~df["segment"].isin(VALID_SEGMENTS)]
    if not bad_seg.empty:
        raise DataError(
            f"Invalid segment value(s) {bad_seg['segment'].unique().tolist()} "
            f"at row(s) {bad_seg.index.tolist()}. Must be one of A-F."
        )

    # ── 7. Select most recent month ───────────────────────────────────────────
    months = df["month"].unique().tolist()
    if len(months) > 1:
        logger.info("Multiple months found: %s — selecting most recent", months)
        # Sort lexicographically; assumes format "Jul 2026" etc.
        # Convert to (year, month_num) for correct ordering
        from datetime import datetime

        def _month_key(m: str) -> tuple[int, int]:
            try:
                dt = datetime.strptime(m.strip(), "%b %Y")
                return (dt.year, dt.month)
            except ValueError:
                return (0, 0)

        latest_month = max(months, key=_month_key)
        df = df[df["month"] == latest_month].copy()
        logger.info("Using month: %s (%d rows)", latest_month, len(df))

    if df.empty:
        raise DataError("No data rows remain after month filtering.")

    # ── 8. Deduplicate rider_id (keep highest score per rider in this month) ──
    df = df.sort_values("final_delivery_quality_score", ascending=False)
    df = df.drop_duplicates(subset=["rider_id"], keep="first")

    # ── 9. Name lookup & integrity check ─────────────────────────────────────
    unmatched: list[str] = []
    rows: list[ProcessedRow] = []

    for _, row in df.iterrows():
        rid = str(row["rider_id"])
        name = rider_lookup.get(rid)
        if name is None:
            unmatched.append(rid)
            continue

        percent = round(float(row["final_delivery_quality_score"]) * 100)
        rows.append(
            ProcessedRow(
                rider_id=rid,
                name=name,
                orders=int(row["completed_orders"]),
                on_time=int(row["completed_orders_in_time"]),
                percent=percent,
                segment=str(row["segment"]),
                city=str(row["city_name"]),
                month=str(row["month"]),
            )
        )

    if unmatched:
        raise DataError(
            f"{len(unmatched)} rider ID(s) not found in the master list: "
            f"{unmatched}. Please update نس.pdf or rider_names.json."
        )

    # ── 10. Sort descending by percent (score) ────────────────────────────────
    rows.sort(key=lambda r: r.percent, reverse=True)

    logger.info("Processed %d riders successfully", len(rows))
    return rows


def rows_to_preview(rows: list[ProcessedRow]) -> list[dict[str, Any]]:
    """Convert ProcessedRow list to JSON-serialisable preview dicts."""
    return [
        {
            "sr": i + 1,
            "rider_id": r.rider_id,
            "name": r.name,
            "orders": r.orders,
            "on_time": r.on_time,
            "percent": f"{r.percent}%",
            "segment": r.segment,
            "city": r.city,
        }
        for i, r in enumerate(rows)
    ]
