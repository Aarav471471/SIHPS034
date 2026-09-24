"""Consumer-facing API contracts."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ScanResponse(BaseModel):
    """The 'Scan Before You Buy' card -- spec section 6.A."""

    barcode: str
    found: bool
    message: str | None = None

    product_name: str | None = None
    brand_name: str | None = None
    category: str | None = None

    official_mrp: float | None = None
    net_quantity: str | None = None
    unit_price: str | None = None
    country_of_origin: str | None = None

    compliance_score: int | None = None
    badge_level: str | None = None
    fssai_number: str | None = None
    fssai_verified: bool = False
    past_violations: int = 0
    total_inspections: int = 0
    last_inspected: datetime | None = None

    # Price-gouging radar verdict
    scanned_mrp: float | None = None
    is_price_gouged: bool = False
    gouging_severity: str | None = None
    overcharge_amount: float | None = None
    overcharge_pct: float | None = None
    anomaly_warning: str | None = None
    crowd_modal_mrp: float | None = None
    crowd_sample_count: int = 0


class ReportSubmitResponse(BaseModel):
    report_id: str
    status: str
    reporter_trust_score: float
    priority_score: float
    queue_guidance: str


class CitizenReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    report_ref: str
    store_name: str
    store_address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    violation_category: str | None = None
    citizen_remarks: str | None = None
    image_path: str | None = None
    barcode: str | None = None
    claimed_mrp: float | None = None
    charged_price: float | None = None
    status: str
    priority_score: float
    officer_notes: str | None = None
    verified_at: datetime | None = None
    created_at: datetime | None = None


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    barcode: str | None = None
    alert_type: str
    severity: str | None = None
    title: str
    message: str
    action_url: str | None = None
    is_read: bool = False
    created_at: datetime | None = None


class TrustProfile(BaseModel):
    trust_score: float
    badge: str
    verified_reporter: bool
    reports_submitted: int
    reports_confirmed: int
    reports_rejected: int
    accuracy_rate: float | None = None
    rank: int
    total_reporters: int
    next_badge: str | None = None
    reports_to_next_badge: int | None = None
    how_it_works: str
