"""Inspection session API contracts."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Surface = Literal["FRONT", "BACK", "SIDE", "BOTTOM", "CAP", "DIE_LINE"]


class SessionCreate(BaseModel):
    product_name: str | None = Field(default=None, max_length=200)
    brand_name: str | None = Field(default=None, max_length=100)
    barcode: str | None = Field(default=None, max_length=50)
    category_id: int | None = None
    product_category: str | None = None

    package_width_cm: float | None = Field(default=None, gt=0, le=500)
    package_height_cm: float | None = Field(default=None, gt=0, le=500)

    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    store_name: str | None = Field(default=None, max_length=150)
    location_address: str | None = None

    # Set by the offline PWA when replaying a queued capture, so the finding is
    # dated to when the officer was actually in the shop.
    captured_at: datetime | None = None


class ImageUploadResponse(BaseModel):
    image_id: int
    surface_type: str
    sha256_hash: str
    perceptual_hash: str | None = None
    width_px: int | None = None
    height_px: int | None = None
    size_bytes: int | None = None
    url: str | None = None
    duplicate_warning: str | None = None


class ExtractedFieldOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    field_name: str
    detected_value: str | None = None
    surface_found: str | None = None
    bbox_x: int | None = None
    bbox_y: int | None = None
    bbox_width: int | None = None
    bbox_height: int | None = None
    confidence_vision_llm: float | None = None
    confidence_ocr_verify: float | None = None
    ocr_agreement: bool | None = None
    ocr_read_value: str | None = None
    raw_pixel_crop_path: str | None = None
    crop_url: str | None = None
    font_height_mm: float | None = None
    effective_confidence: float | None = None


class ViolationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    rule_id: str
    rule_name: str | None = None
    field_name: str | None = None
    status: str
    severity: str | None = None
    evidence_text: str | None = None
    legal_clause: str | None = None
    confidence: float | None = None
    calculated_value: str | None = None
    expected_value: str | None = None
    discrepancy: str | None = None
    suggested_fix: str | None = None
    penalty_amount: float | None = None
    evidence_crop_path: str | None = None
    crop_url: str | None = None


class SessionImageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    surface_type: str
    image_path: str
    url: str | None = None
    sha256_hash: str
    image_width_px: int | None = None
    image_height_px: int | None = None
    is_curved_surface: bool = False
    curvature_score: float | None = None
    unwarp_method: str | None = None
    px_per_mm: float | None = None
    uploaded_at: datetime | None = None


class SessionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: str
    status: str
    source_type: str | None = None
    overall_score: int | None = None
    compliance_status: str | None = None
    confidence_score: float | None = None
    estimated_penalty: float | None = None
    brand_name: str | None = None
    product_name: str | None = None
    product_category: str | None = None
    barcode: str | None = None
    barcode_verified: bool = False
    store_name: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    jurisdiction_status: str | None = None
    is_locked: bool = False
    created_at: datetime | None = None
    completed_at: datetime | None = None
    violation_count: int = 0


class SessionDetail(SessionSummary):
    location_address: str | None = None
    package_width_cm: float | None = None
    package_height_cm: float | None = None
    surface_area_cm2: float | None = None
    evidence_seal: str | None = None
    processing_error: str | None = None
    officer_name: str | None = None
    officer_id_code: str | None = None

    images: list[SessionImageOut] = []
    fields: list[ExtractedFieldOut] = []
    violations: list[ViolationOut] = []


class ProcessResponse(BaseModel):
    session_id: str
    task_id: str
    status: str
    message: str
    websocket_url: str


class SessionListResponse(BaseModel):
    items: list[SessionSummary]
    total: int
    page: int
    page_size: int


class EscalateRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class PeerReviewDecision(BaseModel):
    decision: Literal["APPROVED", "REJECTED", "MODIFIED"]
    remarks: str = Field(min_length=3, max_length=2000)


class PipelineDiagnostics(BaseModel):
    """Exposed so the officer console can show what the pipeline actually did."""

    vision_provider: str
    ocr_engine: str
    surfaces: list[dict[str, Any]] = []
    timings_ms: dict[str, int] = {}
    warnings: list[str] = []
