"""brand_disputes -- spec section 4 / Dispute & Appeal Workflow (spec 3.G).

Due process: the brand receives a secure token, has DISPUTE_WINDOW_DAYS to view
the exact pixel crops cited against it, and may file counter-evidence before an
appellate officer decides.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, JSONVariant, created_at_col, UTCDateTime
from models.enums import AppellateStatus

if TYPE_CHECKING:
    from models.inspection_session import InspectionSession
    from models.user import User


class BrandDispute(Base):
    __tablename__ = "brand_disputes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("inspection_sessions.id"), nullable=False, index=True
    )
    brand_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    brand_name: Mapped[str | None] = mapped_column(String(100))

    dispute_token: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    token_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    grounds_of_appeal: Mapped[str | None] = mapped_column(Text)
    counter_evidence_urls: Mapped[list[Any] | None] = mapped_column(JSONVariant)

    appellate_status: Mapped[str] = mapped_column(
        String(30), default=AppellateStatus.UNDER_REVIEW, nullable=False, index=True
    )
    appellate_officer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    appellate_remarks: Mapped[str | None] = mapped_column(Text)
    hearing_date: Mapped[datetime | None] = mapped_column(UTCDateTime)
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = created_at_col()

    session: Mapped["InspectionSession"] = relationship()
    brand: Mapped["User | None"] = relationship(foreign_keys=[brand_id])
    appellate_officer: Mapped["User | None"] = relationship(foreign_keys=[appellate_officer_id])

    @property
    def is_submitted(self) -> bool:
        return bool(self.grounds_of_appeal)
