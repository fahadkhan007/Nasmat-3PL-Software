"""
test_csv_processor.py
---------------------
Unit tests for core/csv_processor.py
"""

from __future__ import annotations

import io

import pandas as pd
import pytest

from core.csv_processor import DataError, process_csv
from models.schemas import ProcessedRow

# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_csv(**overrides) -> bytes:
    """Build a minimal valid single-row CSV, with optional field overrides."""
    row = {
        "month": "Jul 2026",
        "city_name": "Eastern province",
        "contract_name": "nasamat_alsharq_ebc_shift_ftr",
        "rider_id": "4709799",
        "total_verification_requests": "51",
        "successful_verification_requests": "51",
        "verification_success_rate": "1",
        "gross_orders": "610",
        "completed_orders": "606",
        "completed_orders_in_time": "601",
        "failed_orders_by_rider": "0",
        "on_time_delivery_score": "0.99",
        "fail_rate_score": "1",
        "final_delivery_quality_score": "0.9958745874587458",
        "segment": "A",
        **overrides,
    }
    df = pd.DataFrame([row])
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()


MINIMAL_LOOKUP = {"4709799": "مصطفى العبدلي", "4755316": "جعفر"}


# ── Valid CSV tests ────────────────────────────────────────────────────────────

class TestValidCsv:
    def test_processes_sample_csv(self, sample_csv_bytes, rider_lookup):
        rows = process_csv(sample_csv_bytes, rider_lookup)
        assert len(rows) > 0

    def test_returns_list_of_processed_rows(self, sample_csv_bytes, rider_lookup):
        rows = process_csv(sample_csv_bytes, rider_lookup)
        assert all(isinstance(r, ProcessedRow) for r in rows)

    def test_all_54_unique_riders_jul(self, sample_csv_bytes, rider_lookup):
        """Sample CSV has 54 unique riders in Jul 2026 (most recent month)."""
        rows = process_csv(sample_csv_bytes, rider_lookup)
        assert len(rows) == 54

    def test_sorted_descending_by_percent(self, sample_csv_bytes, rider_lookup):
        rows = process_csv(sample_csv_bytes, rider_lookup)
        percents = [r.percent for r in rows]
        assert percents == sorted(percents, reverse=True), \
            "Rows must be sorted by percent descending"

    def test_most_recent_month_selected(self, sample_csv_bytes, rider_lookup):
        """CSV contains Jun 2026 and Jul 2026 — only Jul 2026 rows should appear."""
        rows = process_csv(sample_csv_bytes, rider_lookup)
        months = {r.month for r in rows}
        assert months == {"Jul 2026"}, f"Expected only Jul 2026, got {months}"

    def test_percent_conversion_correct(self):
        """Score 0.9958... → 100% (rounded)."""
        rows = process_csv(_make_csv(), MINIMAL_LOOKUP)
        assert rows[0].percent == 100

    def test_percent_96_conversion(self):
        rows = process_csv(
            _make_csv(final_delivery_quality_score="0.9617647058823529"),
            MINIMAL_LOOKUP,
        )
        assert rows[0].percent == 96

    def test_name_is_matched(self):
        rows = process_csv(_make_csv(), MINIMAL_LOOKUP)
        assert rows[0].name == "مصطفى العبدلي"

    def test_first_row_has_best_score(self, sample_csv_bytes, rider_lookup):
        rows = process_csv(sample_csv_bytes, rider_lookup)
        assert rows[0].percent >= rows[-1].percent

    def test_segment_values_valid(self, sample_csv_bytes, rider_lookup):
        rows = process_csv(sample_csv_bytes, rider_lookup)
        for r in rows:
            assert r.segment in {"A", "B", "C", "D", "E", "F"}

    def test_on_time_le_orders(self, sample_csv_bytes, rider_lookup):
        rows = process_csv(sample_csv_bytes, rider_lookup)
        for r in rows:
            assert r.on_time <= r.orders, \
                f"Rider {r.rider_id}: on_time ({r.on_time}) > orders ({r.orders})"


# ── Validation failure tests ───────────────────────────────────────────────────

class TestValidationErrors:
    def test_empty_csv_raises(self):
        with pytest.raises(DataError):
            process_csv(b"", MINIMAL_LOOKUP)

    def test_missing_required_column_raises(self):
        # Remove segment column
        csv = _make_csv()
        df = pd.read_csv(io.BytesIO(csv))
        df = df.drop(columns=["segment"])
        buf = io.BytesIO(); df.to_csv(buf, index=False)
        with pytest.raises(DataError, match="segment"):
            process_csv(buf.getvalue(), MINIMAL_LOOKUP)

    def test_missing_rider_id_column_raises(self):
        csv = _make_csv()
        df = pd.read_csv(io.BytesIO(csv))
        df = df.drop(columns=["rider_id"])
        buf = io.BytesIO(); df.to_csv(buf, index=False)
        with pytest.raises(DataError, match="rider_id"):
            process_csv(buf.getvalue(), MINIMAL_LOOKUP)

    def test_score_above_1_raises(self):
        with pytest.raises(DataError, match="out of"):
            process_csv(_make_csv(final_delivery_quality_score="1.5"), MINIMAL_LOOKUP)

    def test_score_below_0_raises(self):
        with pytest.raises(DataError, match="out of"):
            process_csv(_make_csv(final_delivery_quality_score="-0.1"), MINIMAL_LOOKUP)

    def test_invalid_segment_raises(self):
        with pytest.raises(DataError, match="segment"):
            process_csv(_make_csv(segment="Z"), MINIMAL_LOOKUP)

    def test_unmatched_rider_raises(self):
        lookup = {}  # empty lookup → nothing matches
        with pytest.raises(DataError, match="not found"):
            process_csv(_make_csv(), lookup)

    def test_non_csv_content_raises(self):
        with pytest.raises(DataError):
            process_csv(b"%PDF-1.4 garbage", MINIMAL_LOOKUP)

    def test_non_numeric_score_raises(self):
        with pytest.raises(DataError, match="non-numeric"):
            process_csv(_make_csv(final_delivery_quality_score="abc"), MINIMAL_LOOKUP)
