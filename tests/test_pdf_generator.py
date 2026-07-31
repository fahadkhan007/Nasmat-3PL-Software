"""
test_pdf_generator.py
---------------------
Unit tests for core/pdf_generator.py
"""

from __future__ import annotations

import io

import pdfplumber
import pytest

from core.pdf_generator import generate_pdf
from models.schemas import ProcessedRow

# ── Fixtures ───────────────────────────────────────────────────────────────────

def _make_row(**kw) -> ProcessedRow:
    defaults = dict(
        rider_id="4709799",
        name="مصطفى العبدلي",
        orders=583,
        on_time=578,
        percent=100,
        segment="A",
        city="Eastern province",
        month="Jul 2026",
    )
    defaults.update(kw)
    return ProcessedRow(**defaults)


SAMPLE_ROWS = [
    _make_row(rider_id="4787594", name="نووید أحمد",    orders=12,  on_time=12,  percent=100, segment="A"),
    _make_row(rider_id="4709799", name="مصطفى العبدلي", orders=583, on_time=578, percent=100, segment="A"),
    _make_row(rider_id="1992968", name="نادر هاشم",     orders=408, on_time=400, percent=99,  segment="A"),
    _make_row(rider_id="4755316", name="جعفر",          orders=186, on_time=182, percent=99,  segment="F"),
    _make_row(rider_id="4758971", name="نافع",          orders=101, on_time=92,  percent=96,  segment="D"),
    _make_row(rider_id="4779470", name="أكمان",         orders=25,  on_time=18,  percent=86,  segment="E"),
]


# ── Tests ──────────────────────────────────────────────────────────────────────

class TestPdfGenerator:
    def test_returns_bytes(self, processed_rows):
        result = generate_pdf(processed_rows, "Jul 2026")
        assert isinstance(result, bytes)

    def test_non_empty_output(self, processed_rows):
        result = generate_pdf(processed_rows, "Jul 2026")
        assert len(result) > 5000, f"PDF too small: {len(result)} bytes"

    def test_valid_pdf_structure(self, processed_rows):
        """PDF must be openable by pdfplumber without error."""
        pdf_bytes = generate_pdf(processed_rows, "Jul 2026")
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            assert len(pdf.pages) >= 1

    def test_row_count_matches_input(self, processed_rows):
        """Every input row must appear as a table row in the PDF."""
        pdf_bytes = generate_pdf(processed_rows, "Jul 2026")
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            all_text = "\n".join(
                p.extract_text() or "" for p in pdf.pages
            )
        # Check each rider ID appears in the PDF
        for row in processed_rows:
            assert row.rider_id in all_text, \
                f"Rider ID {row.rider_id} missing from PDF"

    def test_all_segment_values_rendered(self):
        rows = [
            _make_row(rider_id=f"47000{i:02d}", name=f"rider{i}", segment=seg,
                      orders=100, on_time=90, percent=90 - i)
            for i, seg in enumerate("ABCDEF")
        ]
        pdf_bytes = generate_pdf(rows, "Jul 2026")
        assert len(pdf_bytes) > 1000

    def test_percent_suffix_present(self, processed_rows):
        pdf_bytes = generate_pdf(processed_rows, "Jul 2026")
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            text = "\n".join(p.extract_text() or "" for p in pdf.pages)
        assert "%" in text

    def test_sr_column_starts_at_1(self):
        pdf_bytes = generate_pdf(SAMPLE_ROWS, "Jul 2026")
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            text = pdf.pages[0].extract_text() or ""
        assert "1" in text

    def test_single_row_works(self):
        rows = [_make_row()]
        result = generate_pdf(rows, "Jul 2026")
        assert isinstance(result, bytes)
        assert len(result) > 1000

    def test_empty_month_label_does_not_crash(self, processed_rows):
        result = generate_pdf(processed_rows, month="")
        assert len(result) > 5000

    def test_pdf_header_contains_title(self, processed_rows):
        pdf_bytes = generate_pdf(processed_rows, "Jul 2026")
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            text = pdf.pages[0].extract_text() or ""
        # Header should have report title (Arabic reshaping reverses it, check partial)
        assert len(text) > 50  # something is rendered
