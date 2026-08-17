from __future__ import annotations
# pyrefly: ignore [invalid-syntax]
from models.schemas import RiderResponse
from fastapi.openapi.utils import status_code_ranges
from models.schemas import RiderRequest

# pyrefly: ignore [invalid-syntax]

from importlib import import_module
from fastapi import status
import logging
from contextlib import asynccontextmanager
from typing import Any
from datetime import datetime

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import io

from core.csv_processor import DataError, process_csv, rows_to_preview
from core.pdf_generator import generate_pdf
from core.rider_parser import build_rider_lookup
from core.performance_processor import process_performance_csv, perf_rows_to_preview
from core.performance_pdf_generator import generate_performance_pdf
from models.schemas import GenerateRequest, UploadResponse, RiderAdd, RiderDelete, PerformanceRow, PerfGenerateRequest
from helper.json_helper import read_json, write_json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Shared state (loaded once at startup) ─────────────────────────────────────
_rider_lookup: dict[str, str] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load rider lookup at startup — fail fast if PDFs are missing or corrupt."""
    global _rider_lookup
    logger.info("Loading rider lookup…")
    try:
        _rider_lookup = build_rider_lookup()
        logger.info("Rider lookup ready: %d entries", len(_rider_lookup))
    except Exception as exc:
        logger.critical("STARTUP FAILED — could not build rider lookup: %s", exc)
        raise
    yield
    logger.info("Shutting down.")

JSON_FILE="rider_names.json"

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="3PL Report Generator",
    description="Upload your daily 3PL CSV and download the formatted PDF report.",
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/image", StaticFiles(directory="image"), name="image")
templates = Jinja2Templates(directory="templates")


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html")


@app.post("/upload")
async def upload_csv(file: UploadFile = File(...)) -> JSONResponse:
    """
    Accept a CSV file, validate it, match rider names, and return a
    JSON preview + the ProcessedRow data needed by /generate.
    """
    # ── File type guard ────────────────────────────────────────────────────────
    fname = file.filename or ""
    if not fname.lower().endswith(".csv"):
        raise HTTPException(
            status_code=415,
            detail="Only .csv files are accepted. Please upload your 3PL report CSV.",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="The uploaded file is empty.")

    # ── Process ────────────────────────────────────────────────────────────────
    try:
        rows = process_csv(content, _rider_lookup)
    except DataError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.exception("Unexpected error while processing CSV")
        raise HTTPException(status_code=500, detail=f"Internal error: {exc}")

    month = rows[0].month if rows else ""
    preview = rows_to_preview(rows)

    return JSONResponse({
        "month": month,
        "total_riders": len(rows),
        "rows": preview,
        # Full row data passed back for the /generate endpoint
        "_rows": [r.model_dump() for r in rows],
    })


@app.post("/generate")
async def generate_report(request: GenerateRequest) -> StreamingResponse:
    """
    Accept the validated row data from /upload and return a PDF download.
    """
    if not request.rows:
        raise HTTPException(status_code=422, detail="No rows provided.")

    try:
        pdf_bytes = generate_pdf(request.rows, month=request.month)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=f"Font file missing: {exc}")
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        logger.exception("Unexpected error while generating PDF")
        raise HTTPException(status_code=500, detail=f"Internal error: {exc}")

    month_slug = request.month.replace(" ", "_")
    filename = f"3PL_Report_{month_slug}.pdf"

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


password="hello123"

@app.post("/rider", status_code=status.HTTP_201_CREATED)
async def add_rider(item : RiderAdd) -> str:

    if(item.password!=password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid password"
        )

    db_data=await read_json(JSON_FILE)
    
    if item.rider_id in db_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="rider already exists"
        )

    db_data[item.rider_id] = item.name
    await write_json(JSON_FILE, db_data)
    
    # Update in-memory lookup
    _rider_lookup[item.rider_id] = item.name
    
    return "rider inserted successfully!"

@app.delete("/rider", status_code=status.HTTP_200_OK)
async def delete_rider(item: RiderDelete) -> str:
    if(item.password!=password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid password"
        )

    db_data=await read_json(JSON_FILE)

    if item.rider_id not in db_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="rider not found"
        )

    del db_data[item.rider_id]
    await write_json(JSON_FILE, db_data)
    
    # Update in-memory lookup
    if item.rider_id in _rider_lookup:
        del _rider_lookup[item.rider_id]
        
    return "rider deleted successfully!"

@app.get("/riders", status_code=status.HTTP_200_OK)
async def get_rider(req_password: str) -> RiderResponse:
    if req_password != password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized access, Denied!"
        )

    ordered_data = [{"id": k, "name": v} for k, v in _rider_lookup.items()]
    return RiderResponse(data=ordered_data)

@app.get("/search", status_code=status.HTTP_200_OK)
async def search_rider(query: str)-> list[dict]:
    query=query.strip().lower()
    if not query:
        return []

    result=[]

    for rider_id, names in _rider_lookup.items():
        if query in rider_id.lower() or query in names.lower():
            result.append({"id": rider_id, "name": names})
    return result

@app.get("/health")
async def health() -> dict[str, Any]:
    """Health check endpoint for Render.com."""
    return {
        "status": "ok",
        "riders_loaded": len(_rider_lookup),
    }


# ── Performance Report Routes ─────────────────────────────────────────────────

@app.post("/upload-performance")
async def upload_performance_csv(file: UploadFile = File(...)) -> JSONResponse:
    """
    Accept a 3PL Performance CSV, validate it, match rider names, and return
    a JSON preview + the PerformanceRow data needed by /generate-performance.
    Unmatched rider IDs are returned as a 'warnings' list instead of raising.
    """
    fname = file.filename or ""
    if not fname.lower().endswith(".csv"):
        raise HTTPException(
            status_code=415,
            detail="Only .csv files are accepted. Please upload your 3PL Performance CSV.",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="The uploaded file is empty.")

    try:
        rows, unmatched = process_performance_csv(content, _rider_lookup)
    except DataError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.exception("Unexpected error while processing Performance CSV")
        raise HTTPException(status_code=500, detail=f"Internal error: {exc}")

    report_date = datetime.now().strftime("%b %Y")
    preview = perf_rows_to_preview(rows)

    return JSONResponse({
        "report_date": report_date,
        "total_riders": len(rows),
        "rows": preview,
        # Full row data passed back for the /generate-performance endpoint
        "_rows": [r.model_dump() for r in rows],
        # Rider IDs not found in rider_names.json
        "warnings": unmatched,
    })


@app.post("/generate-performance")
async def generate_performance_report(request: PerfGenerateRequest) -> StreamingResponse:
    """
    Accept the validated performance row data and return a landscape PDF download.
    """
    if not request.rows:
        raise HTTPException(status_code=422, detail="No rows provided.")

    try:
        pdf_bytes = generate_performance_pdf(request.rows, report_date=request.report_date)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=f"Font file missing: {exc}")
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        logger.exception("Unexpected error while generating Performance PDF")
        raise HTTPException(status_code=500, detail=f"Internal error: {exc}")

    date_slug = request.report_date.replace(" ", "_")
    filename  = f"3PL_Performance_Report_{date_slug}.pdf"

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
