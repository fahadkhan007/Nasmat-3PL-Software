"""
conftest.py — Shared pytest fixtures
"""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

BASE_DIR = Path(__file__).parent.parent
SAMPLE_CSV = BASE_DIR / "3PL Report_Delivery Quality Segmentation_Table (1).csv"


@pytest.fixture(scope="session")
def sample_csv_bytes() -> bytes:
    """Raw bytes of the real sample CSV (committed to the repo)."""
    return SAMPLE_CSV.read_bytes()


@pytest.fixture(scope="session")
def rider_lookup() -> dict[str, str]:
    """Built rider lookup using actual PDFs."""
    from core.rider_parser import build_rider_lookup
    return build_rider_lookup()


@pytest.fixture()
def processed_rows(sample_csv_bytes, rider_lookup):
    """Fully processed rows from the real CSV."""
    from core.csv_processor import process_csv
    return process_csv(sample_csv_bytes, rider_lookup)


@pytest.fixture()
async def async_client():
    """Async HTTPX client wired to the FastAPI app."""
    from app import app
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
