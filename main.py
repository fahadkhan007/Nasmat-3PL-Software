# Entry point — re-exports the FastAPI app so uvicorn can be run as:
#   uv run uvicorn main:app --reload
# or equivalently:
#   uv run uvicorn app:app --reload

from app import app  # noqa: F401

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
