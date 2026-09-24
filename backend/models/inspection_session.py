"""inspection_sessions -- spec section 4.

The immutable inspection ledger.  One session aggregates every surface image of
a single physical pack (or a brand die-line), the fields extracted from them,
and the violations the rule engine raised.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, created_at_col, UTCDateTime
from models.enums import ComplianceStatus, SessionStatus, SourceType

if TYPE_CHECKING:
    from models.citizen_report import CitizenReport
    from models.extracted_field import ExtractedField
    from models.peer_review import PeerReview
    from models.session_image import SessionImage
    from models.user import User
    from models.violation import Violation


class InspectionSession(Base):
    __tablename__ = "inspection_sessions"
    __table_args__ = (
        Index("idx_session_status", "status"),
        Index("idx_session_barcode", "barcode"),
        Index("idx_session_created", "created_at"),
        Index("idx_session_geo", "latitude", "longitude"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    officer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    source_type: Mapped[str] = mapped_column(
        String(20), default=SourceType.OFFICER, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(30), default=SessionStatus.PENDING, nullable=False
    )

    # --- results ---
    overall_score: Mapped[int | None] = mapped_column(Integer)
    compliance_status: Mapped[str | None] = mapped_column(String(20))
    confidence_score: Mapped[float | None] = mapped_column(Float)
    estimated_penalty: Mapped[float | None] = mapped_column(Float)

    # --- pack geometry (drives the Rule 11 font-height ratio check) ---
    package_width_cm: Mapped[float | None] = mapped_column(Float)
    package_height_cm: Mapped[float | None] = mapped_column(Float)
    surface_area_cm2: Mapped[float | None] = mapped_column(Float)

    # --- product identity ---
    product_category: Mapped[str | None] = mapped_column(String(100))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"))
    brand_name: Mapped[str | None] = mapped_column(String(100), index=True)
    product_name: Mapped[str | None] = mapped_column(String(200))
    barcode: Mapped[str | None] = mapped_column(String(50))
    barcode_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # --- location & jurisdiction ---
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    store_name: Mapped[str | None] = mapped_column(String(150), index=True)
    location_address: Mapped[str | None] = mapped_column(Text)
    jurisdiction_status: Mapped[str | None] = mapped_column(String(30))

    # --- evidence integrity ---
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    evidence_seal: Mapped[str | None] = mapped_column(String(64))
    processing_error: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = created_at_col()
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    # --- relationships ---
    officer: Mapped["User | None"] = relationship(
        back_populates="sessions", foreign_keys=[officer_id]
    )
    images: Mapped[list["SessionImage"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    fields: Mapped[list["ExtractedField"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    violations: Mapped[list["Violation"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    peer_reviews: Mapped[list["PeerReview"]] = relationship(back_populates="session")
    citizen_report: Mapped["CitizenReport | None"] = relationship(back_populates="session")

    # --- convenience ---
    @property
    def is_terminal(self) -> bool:
        return self.status in (
            SessionStatus.COMPLETED,
            SessionStatus.RESOLVED,
            SessionStatus.FAILED,
        )

    @property
    def failed_violations(self) -> list["Violation"]:
        return [v for v in self.violations if v.status == "FAIL"]

    def compute_compliance_status(self) -> str:
        fails = sum(1 for v in self.violations if v.status == "FAIL")
        warns = sum(1 for v in self.violations if v.status == "WARNING")
        if fails:
            return ComplianceStatus.NON_COMPLIANT
        if warns:
            return ComplianceStatus.WARNING
        return ComplianceStatus.COMPLIANT
