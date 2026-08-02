"""
schemas.py
----------
Pydantic models for strict runtime type validation across the entire pipeline.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


SEGMENT_LITERAL = Literal["A", "B", "C", "D", "E", "F"]


class ProcessedRow(BaseModel):
    """A single validated, name-enriched rider record ready for PDF output."""

    rider_id: str = Field(..., min_length=6, max_length=8)
    name: str = Field(..., min_length=1)
    orders: int = Field(..., ge=0)
    on_time: int = Field(..., ge=0)
    percent: int = Field(..., ge=0, le=100)
    segment: SEGMENT_LITERAL
    city: str
    month: str

    @field_validator("on_time")
    @classmethod
    def on_time_le_orders(cls, v: int, info) -> int:  # noqa: N805
        orders = info.data.get("orders", 0)
        if v > orders:
            raise ValueError(
                f"on_time ({v}) cannot exceed orders ({orders})"
            )
        return v


class RiderPreview(BaseModel):
    """JSON response for the /upload endpoint — preview table data."""

    sr: int
    rider_id: str
    name: str
    orders: int
    on_time: int
    percent: str   # e.g. "97%"
    segment: SEGMENT_LITERAL
    city: str


class UploadResponse(BaseModel):
    """Full response from POST /upload."""

    month: str
    total_riders: int
    rows: list[RiderPreview]


class GenerateRequest(BaseModel):
    """Request body for POST /generate."""

    month: str
    rows: list[ProcessedRow]

class RiderAdd(BaseModel):
    rider_id : str
    name : str
    password: str

class RiderDelete(BaseModel):
    rider_id: str
    password: str


class RiderRequest(BaseModel):
    password: str

class RiderResponse(BaseModel):
    data: dict