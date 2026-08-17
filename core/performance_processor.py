"""
performance_processor.py
------------------------
Validates, parses, and enriches the 3PL Rider Performance CSV.

Strict rules (any violation raises DataError with actionable message):
  - All required columns must be present
  - Numeric columns must contain valid numbers
  - Rate fields (attendance, acceptance) must be in [0.0, 1.0]

Soft rule (warning, not error):
  - Riders not in the lookup are collected and returned as a warning list;
    the PDF is still generated for matched riders.

Output is sorted by completed_deliveries descending.
"""

from __future__ import annotations

import io
import logging
from typing import Any

import pandas as pd

from core.csv_processor import DataError  # shared exception — no duplication
from models.schemas import PerformanceRow

logger = logging.getLogger(__name__)

# Columns we strictly require (after lowercasing CSV headers)
REQUIRED_COLUMNS = {
    "rider id",
    "completed deliveries",
    "# shifts",
    "planned working hours",
    "actual working hours",
    "attendance rate",
    "break hours",
    "lost hours",
    "acceptance rate",
    "declined deliveries",
}


def process_performance_csv(
    content: bytes,
    rider_lookup: dict[str, str],
) -> tuple[list[PerformanceRow], list[str]]:
    """
    Parse raw performance CSV bytes, validate every field, join rider names,
    and return a sorted list of PerformanceRow + a list of unmatched rider IDs.

    Args:
        content:       Raw bytes of the uploaded performance CSV file.
        rider_lookup:  Dict mapping rider_id (str) → Arabic name (str).

    Returns:
        Tuple of:
          - list[PerformanceRow] sorted by completed_deliveries descending
          - list[str] of rider_ids not found in the lookup (warning list)

    Raises:
        DataError: On any structural / integrity failure (CSV parse error,
                   missing columns, non-numeric values, rate out of range).
    """
    # ── 1. Parse CSV ──────────────────────────────────────────────────────────
    try:
        df = pd.read_csv(io.BytesIO(content), dtype=str)
    except Exception as exc:
        raise DataError(f"Could not parse CSV: {exc}") from exc

    if df.empty:
        raise DataError("The uploaded CSV file is empty.")

    # Normalise column names: lowercase + strip whitespace
    df.columns = [c.strip().lower() for c in df.columns]

    # ── 2. Column presence check ──────────────────────────────────────────────
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise DataError(
            f"Missing required column(s): {', '.join(sorted(missing))}. "
            "Make sure you are uploading the Rider Performance CSV (not the "
            "Delivery Quality report)."
        )

    # ── 3. Strip whitespace from all string cells ─────────────────────────────
    df = df.apply(
        lambda col: col.map(lambda x: x.strip() if isinstance(x, str) else x)
    )

    # ── 4. Type coercion — integer columns ───────────────────────────────────
    for col in ("# shifts", "declined deliveries"):
        try:
            df[col] = df[col].astype(float).astype(int)
        except (ValueError, TypeError):
            raise DataError(f"Column '{col}' must contain whole numbers.")

    # completed deliveries coerced separately for dedup sort
    try:
        df["completed deliveries"] = df["completed deliveries"].astype(float).astype(int)
    except (ValueError, TypeError):
        raise DataError("Column 'completed deliveries' must contain whole numbers.")

    # ── 5. Type coercion — float columns ─────────────────────────────────────
    float_cols = (
        "planned working hours",
        "actual working hours",
        "break hours",
        "lost hours",
        "attendance rate",
        "acceptance rate",
    )
    for col in float_cols:
        try:
            df[col] = df[col].astype(float)
        except (ValueError, TypeError):
            raise DataError(f"Column '{col}' contains non-numeric values.")

    # ── 6. Rate range validation [0.0, 1.0] ──────────────────────────────────
    for rate_col in ("attendance rate", "acceptance rate"):
        bad = df[(df[rate_col] < 0.0) | (df[rate_col] > 1.0)]
        if not bad.empty:
            raise DataError(
                f"'{rate_col}' values out of [0, 1] range at "
                f"row(s) {bad.index.tolist()}: {bad[rate_col].tolist()}"
            )

    # ── 7. Deduplicate rider_id (keep highest completed_deliveries per rider) ─
    df = df.sort_values("completed deliveries", ascending=False)
    df = df.drop_duplicates(subset=["rider id"], keep="first")

    # ── 8. Name lookup — soft fail: collect unmatched, don't raise ────────────
    city_col = "city name" if "city name" in df.columns else None
    unmatched: list[str] = []
    rows: list[PerformanceRow] = []

    for _, row in df.iterrows():
        rid = str(row["rider id"])
        name = rider_lookup.get(rid)

        if name is None:
            unmatched.append(rid)
            logger.warning("Performance CSV: rider_id '%s' not in lookup — skipped", rid)
            continue

        rows.append(
            PerformanceRow(
                rider_id=rid,
                name=name,
                completed_deliveries=int(row["completed deliveries"]),
                shifts=int(row["# shifts"]),
                planned_hours=round(float(row["planned working hours"]), 2),
                actual_hours=round(float(row["actual working hours"]), 2),
                attendance_rate=round(float(row["attendance rate"]) * 100),
                break_hours=round(float(row["break hours"]), 2),
                lost_hours=round(float(row["lost hours"]), 2),
                acceptance_rate=round(float(row["acceptance rate"]) * 100),
                declined_deliveries=int(row["declined deliveries"]),
                city=str(row[city_col]) if city_col else "",
            )
        )

    if not rows:
        raise DataError(
            "No riders could be matched from this CSV — none of the rider IDs "
            "are present in the system. Please add riders first."
        )

    # ── 9. Sort by completed_deliveries descending ────────────────────────────
    rows.sort(key=lambda r: r.completed_deliveries, reverse=True)

    logger.info(
        "Performance CSV: %d riders matched, %d unmatched",
        len(rows),
        len(unmatched),
    )
    return rows, unmatched


def perf_rows_to_preview(rows: list[PerformanceRow]) -> list[dict[str, Any]]:
    """
    Convert a PerformanceRow list to JSON-serialisable preview dicts.
    Break / lost hours are formatted as '-' when zero.
    """
    return [
        {
            "sr": i + 1,
            "rider_id": r.rider_id,
            "name": r.name,
            "completed_deliveries": r.completed_deliveries,
            "shifts": r.shifts,
            "planned_hours": r.planned_hours,
            "actual_hours": r.actual_hours,
            "attendance_rate": f"{r.attendance_rate}%",
            "break_hours": "-" if r.break_hours == 0.0 else f"{r.break_hours:.2f}",
            "lost_hours": "-" if r.lost_hours == 0.0 else f"{r.lost_hours:.2f}",
            "acceptance_rate": f"{r.acceptance_rate}%",
            "declined_deliveries": r.declined_deliveries,
        }
        for i, r in enumerate(rows)
    ]
