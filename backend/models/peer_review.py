"""peer_reviews -- spec section 4 / Senior Escalation (spec 3.E).

Escalation is automatic when a case is borderline (confidence 0.60-0.75), when
the unit-price maths is contested, or when the penalty exceeds the configured
threshold.  A senior officer then approves, modifies, or dismisses.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, created_at_col, UTCDateTime
from models.enums import PeerReviewStatus

if TYPE_CHECKING:
    from models.inspection_session import InspectionSession
    from models.user import User


class PeerReview(Base):
    __tablename__ = "peer_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("inspection_sessions.id"), nullable=False, index=True
    )
    requested_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)

    trigger_reason: Mapped[str | None] = mapped_column(String(100))
    trigger_detail: Mapped[str | None] = mapped_column(Text)
    triggering_confidence: Mapped[float | None] = mapped_column(Float)

    review_status: Mapped[str] = mapped_column(
        String(30), default=PeerReviewStatus.PENDING, nullable=False, index=True
    )
    reviewer_remarks: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = created_at_col()

    session: Mapped["InspectionSession"] = relationship(back_populates="peer_reviews")
    requested_by: Mapped["User | None"] = relationship(foreign_keys=[requested_by_id])
    reviewer: Mapped["User | None"] = relationship(foreign_keys=[reviewer_id])
