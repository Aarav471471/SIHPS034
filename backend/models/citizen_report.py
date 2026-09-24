"""citizen_reports -- spec section 4 / Citizen Reporting (spec 3.B).

A crowdsourced violation lead.  Reports from high-trust reporters
(T_rep > 80) jump to the top of the officer's daily priority queue, and the
officer's verdict feeds straight back into the reporter's trust score.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, created_at_col, UTCDateTime
from models.enums import ReportStatus

if TYPE_CHECKING:
    from models.inspection_session import InspectionSession
    from models.user import User


class CitizenReport(Base):
    __tablename__ = "citizen_reports"
    __table_args__ = (
        Index("idx_report_status", "status"),
        Index("idx_report_geo", "latitude", "longitude"),
        Index("idx_report_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_ref: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    session_id: Mapped[int | None] = mapped_column(
        ForeignKey("inspection_sessions.id"), index=True
    )
    reporter_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)

    store_name: Mapped[str] = mapped_column(String(150), nullable=False)
    store_address: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)

    violation_category: Mapped[str | None] = mapped_column(String(50), index=True)
    citizen_remarks: Mapped[str | None] = mapped_column(Text)
    image_path: Mapped[str | None] = mapped_column(String(255))
    barcode: Mapped[str | None] = mapped_column(String(50))
    claimed_mrp: Mapped[float | None] = mapped_column(Float)
    charged_price: Mapped[float | None] = mapped_column(Float)

    status: Mapped[str] = mapped_column(
        String(30), default=ReportStatus.SUBMITTED, nullable=False
    )
    # Trust score of the reporter AT SUBMISSION TIME -- drives queue ordering
    priority_score: Mapped[float] = mapped_column(Float, default=50.0, nullable=False)

    assigned_officer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    officer_notes: Mapped[str | None] = mapped_column(Text)
    verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = created_at_col()

    session: Mapped["InspectionSession | None"] = relationship(back_populates="citizen_report")
    reporter: Mapped["User | None"] = relationship(
        back_populates="reports", foreign_keys=[reporter_id]
    )
    assigned_officer: Mapped["User | None"] = relationship(foreign_keys=[assigned_officer_id])
