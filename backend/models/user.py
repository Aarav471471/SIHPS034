"""users -- spec section 4.

One table serves all five personas (officer, senior_officer, admin, consumer,
brand); role-specific columns are nullable, matching the spec DDL.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, JSONVariant, created_at_col, UTCDateTime
from models.enums import UserRole

if TYPE_CHECKING:
    from models.citizen_report import CitizenReport
    from models.consumer_alert import ConsumerAlert
    from models.inspection_session import InspectionSession


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('officer','senior_officer','admin','consumer','brand')",
            name="valid_role",
        ),
        CheckConstraint(
            "citizen_trust_score >= 0 AND citizen_trust_score <= 100",
            name="trust_score_range",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    full_name: Mapped[str | None] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(20))

    # --- officer / senior_officer ---
    officer_id: Mapped[str | None] = mapped_column(String(50), unique=True)
    department: Mapped[str | None] = mapped_column(String(100))
    jurisdiction_geojson: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant)
    jurisdiction_name: Mapped[str | None] = mapped_column(String(100))

    # --- consumer ---
    citizen_trust_score: Mapped[float] = mapped_column(Float, default=50.0, nullable=False)
    verified_reporter: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reports_submitted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reports_confirmed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # --- brand ---
    brand_id: Mapped[int | None] = mapped_column(Integer)
    brand_name: Mapped[str | None] = mapped_column(String(100), index=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = created_at_col()

    # --- relationships ---
    sessions: Mapped[list["InspectionSession"]] = relationship(
        back_populates="officer",
        foreign_keys="InspectionSession.officer_id",
    )
    reports: Mapped[list["CitizenReport"]] = relationship(
        back_populates="reporter",
        foreign_keys="CitizenReport.reporter_id",
    )
    alerts: Mapped[list["ConsumerAlert"]] = relationship(back_populates="user")

    # --- convenience ---
    @property
    def is_officer(self) -> bool:
        return self.role in (UserRole.OFFICER, UserRole.SENIOR_OFFICER)

    @property
    def is_senior(self) -> bool:
        return self.role in (UserRole.SENIOR_OFFICER, UserRole.ADMIN)

    @property
    def trust_badge(self) -> str | None:
        """'Verified Vigilant Citizen' badge per spec section 3.B."""
        if self.role != UserRole.CONSUMER:
            return None
        return "VERIFIED_VIGILANT_CITIZEN" if self.citizen_trust_score > 80 else "CITIZEN"
