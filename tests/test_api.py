"""
test_api.py
-----------
Integration tests for the FastAPI endpoints.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio

BASE_DIR = Path(__file__).parent.parent
SAMPLE_CSV_PATH = BASE_DIR / "3PL Report_Delivery Quality Segmentation_Table (1).csv"

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture()
async def client():
    from httpx import ASGITransport, AsyncClient
    import app as app_module
    from app import app

    # Pre-load rider lookup so lifespan doesn't need to run during tests
    if not app_module._rider_lookup:
        from core.rider_parser import build_rider_lookup
        app_module._rider_lookup = build_rider_lookup()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c


# ── GET / ─────────────────────────────────────────────────────────────────────

async def test_root_returns_200(client):
    resp = await client.get("/")
    assert resp.status_code == 200


async def test_root_returns_html(client):
    resp = await client.get("/")
    assert "text/html" in resp.headers["content-type"]


async def test_health_endpoint(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["riders_loaded"] >= 54


# ── POST /upload ──────────────────────────────────────────────────────────────

async def test_upload_valid_csv_returns_200(client):
    csv_bytes = SAMPLE_CSV_PATH.read_bytes()
    resp = await client.post(
        "/upload",
        files={"file": ("report.csv", csv_bytes, "text/csv")},
    )
    assert resp.status_code == 200


async def test_upload_returns_correct_schema(client):
    csv_bytes = SAMPLE_CSV_PATH.read_bytes()
    resp = await client.post(
        "/upload",
        files={"file": ("report.csv", csv_bytes, "text/csv")},
    )
    data = resp.json()
    assert "month" in data
    assert "total_riders" in data
    assert "rows" in data
    assert isinstance(data["rows"], list)


async def test_upload_returns_54_riders(client):
    csv_bytes = SAMPLE_CSV_PATH.read_bytes()
    resp = await client.post(
        "/upload",
        files={"file": ("report.csv", csv_bytes, "text/csv")},
    )
    data = resp.json()
    assert data["total_riders"] == 54


async def test_upload_returns_jul_2026(client):
    csv_bytes = SAMPLE_CSV_PATH.read_bytes()
    resp = await client.post(
        "/upload",
        files={"file": ("report.csv", csv_bytes, "text/csv")},
    )
    data = resp.json()
    assert data["month"] == "Jul 2026"


async def test_upload_non_csv_returns_415(client):
    resp = await client.post(
        "/upload",
        files={"file": ("report.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert resp.status_code == 415


async def test_upload_empty_file_returns_422(client):
    resp = await client.post(
        "/upload",
        files={"file": ("empty.csv", b"", "text/csv")},
    )
    assert resp.status_code == 422


async def test_upload_missing_column_returns_422(client):
    bad_csv = b"rider_id,completed_orders\n4709799,100\n"
    resp = await client.post(
        "/upload",
        files={"file": ("bad.csv", bad_csv, "text/csv")},
    )
    assert resp.status_code == 422


async def test_upload_invalid_segment_returns_422(client):
    csv = (
        b"Month,city_name,contract_name,rider_id,total_verification_requests,"
        b"successful_verification_requests,verification_success_rate,"
        b"gross_orders,completed_orders,completed_orders_in_time,"
        b"failed_orders_by_rider,on_time_delivery_score,fail_rate_score,"
        b"final_delivery_quality_score,segment\n"
        b"Jul 2026,Eastern province,test,4709799,1,1,1,100,99,95,0,0.96,1,0.98,Z\n"
    )
    resp = await client.post(
        "/upload",
        files={"file": ("bad.csv", csv, "text/csv")},
    )
    assert resp.status_code == 422


# ── POST /generate ────────────────────────────────────────────────────────────

async def test_generate_returns_pdf(client):
    csv_bytes = SAMPLE_CSV_PATH.read_bytes()
    upload_resp = await client.post(
        "/upload",
        files={"file": ("report.csv", csv_bytes, "text/csv")},
    )
    assert upload_resp.status_code == 200
    data = upload_resp.json()

    gen_resp = await client.post(
        "/generate",
        json={"month": data["month"], "rows": data["_rows"]},
    )
    assert gen_resp.status_code == 200


async def test_generate_content_type_is_pdf(client):
    csv_bytes = SAMPLE_CSV_PATH.read_bytes()
    upload = await client.post(
        "/upload",
        files={"file": ("report.csv", csv_bytes, "text/csv")},
    )
    data = upload.json()
    gen = await client.post(
        "/generate",
        json={"month": data["month"], "rows": data["_rows"]},
    )
    assert "application/pdf" in gen.headers["content-type"]


async def test_generate_content_disposition_has_filename(client):
    csv_bytes = SAMPLE_CSV_PATH.read_bytes()
    upload = await client.post(
        "/upload",
        files={"file": ("report.csv", csv_bytes, "text/csv")},
    )
    data = upload.json()
    gen = await client.post(
        "/generate",
        json={"month": data["month"], "rows": data["_rows"]},
    )
    assert "attachment" in gen.headers.get("content-disposition", "")
    assert ".pdf" in gen.headers.get("content-disposition", "")


async def test_generate_pdf_is_non_empty(client):
    csv_bytes = SAMPLE_CSV_PATH.read_bytes()
    upload = await client.post(
        "/upload",
        files={"file": ("report.csv", csv_bytes, "text/csv")},
    )
    data = upload.json()
    gen = await client.post(
        "/generate",
        json={"month": data["month"], "rows": data["_rows"]},
    )
    assert len(gen.content) > 5000


async def test_generate_empty_rows_returns_422(client):
    resp = await client.post(
        "/generate",
        json={"month": "Jul 2026", "rows": []},
    )
    assert resp.status_code == 422


# ── End-to-end ────────────────────────────────────────────────────────────────

async def test_end_to_end_pipeline(client):
    """Full pipeline: upload CSV → generate PDF → verify PDF contains rider IDs."""
    import io
    import pdfplumber

    csv_bytes = SAMPLE_CSV_PATH.read_bytes()

    upload = await client.post(
        "/upload",
        files={"file": ("report.csv", csv_bytes, "text/csv")},
    )
    assert upload.status_code == 200
    data = upload.json()

    gen = await client.post(
        "/generate",
        json={"month": data["month"], "rows": data["_rows"]},
    )
    assert gen.status_code == 200

    # Verify PDF content
    with pdfplumber.open(io.BytesIO(gen.content)) as pdf:
        all_text = "\n".join(p.extract_text() or "" for p in pdf.pages)

    # Top rider from preview should appear in PDF
    top_rider = data["rows"][0]
    assert top_rider["rider_id"] in all_text, \
        f"Top rider {top_rider['rider_id']} not found in generated PDF"
