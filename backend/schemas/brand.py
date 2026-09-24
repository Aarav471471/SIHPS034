"""Brand pillar API contracts."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class PreCertResponse(BaseModel):
    pre_cert_id: str
    is_compliant: bool
    compliance_score: int
    blocking_issues: int
    digital_badge_token: str | None = None
    audit_report_url: str | None = None
    findings: list[dict[str, Any]] = []
    extracted_declarations: dict[str, str | None] = {}
    measured_font_heights_mm: dict[str, float] = {}
    warnings: list[str] = []
    message: str


class PreCertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cert_ref: str
    product_name: str
    brand_name: str | None = None
    compliance_score: int | None = None
    is_approved: bool = False
    findings: list[Any] | None = None
    digital_badge_token: str | None = None
    target_pack_width_cm: float | None = None
    target_pack_height_cm: float | None = None
    sha256_hash: str | None = None
    created_at: datetime | None = None

    die_line_url: str | None = None
    badge_qr_url: str | None = None
    audit_report_url: str | None = None


class DisputeSubmit(BaseModel):
    grounds_of_appeal: str = Field(min_length=20, max_length=8000)
    evidence_documents: list[str] | None = None


class DisputeDecision(BaseModel):
    decision: Literal["ACCEPTED", "REJECTED"]
    remarks: str = Field(min_length=10, max_length=4000)


class DisputeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dispute_token: str
    brand_name: str | None = None
    grounds_of_appeal: str | None = None
    counter_evidence_urls: list[Any] | None = None
    appellate_status: str
    appellate_remarks: str | None = None
    hearing_date: datetime | None = None
    decided_at: datetime | None = None
    token_expires_at: datetime | None = None
    created_at: datetime | None = None

    is_expired: bool = False
    window_days: int = 15
    session_ref: str | None = None
    product_name: str | None = None
    store_name: str | None = None
    overall_score: int | None = None
    estimated_penalty: float | None = None
    inspected_at: datetime | None = None
    cited_violations: list[dict[str, Any]] = []
    evidence_images: list[dict[str, Any]] = []
