"""Officer intelligence API contracts."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class LeadOut(BaseModel):
    """A citizen report as it appears in the officer queue."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    report_ref: str
    store_name: str
    store_address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    violation_category: str | None = None
    citizen_remarks: str | None = None
    barcode: str | None = None
    claimed_mrp: float | None = None
    charged_price: float | None = None
    status: str
    priority_score: float
    created_at: datetime | None = None

    image_path: str | None = None
    image_url: str | None = None
    reporter_name: str | None = None
    reporter_trust_score: float | None = None
    reporter_verified: bool = False


class LeadVerdict(BaseModel):
    verdict: Literal["VERIFIED", "REJECTED", "INVESTIGATING"]
    notes: str = Field(min_length=3, max_length=2000)


class PeerReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    trigger_reason: str | None = None
    trigger_detail: str | None = None
    triggering_confidence: float | None = None
    review_status: str
    created_at: datetime | None = None

    session_ref: str | None = None
    brand_name: str | None = None
    product_name: str | None = None
    store_name: str | None = None
    overall_score: int | None = None
    estimated_penalty: float | None = None
    violation_count: int = 0
    requested_by_name: str | None = None


class RadarSummary(BaseModel):
    window_days: int
    scans_analysed: int
    products_analysed: int
    findings: int
    priority_findings: int
    hotspots: list[dict[str, Any]] = []
    top_findings: list[dict[str, Any]] = []
