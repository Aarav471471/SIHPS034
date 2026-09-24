"""violations -- spec section 4.

A violation is always traceable to (a) the rule that fired, (b) the legal clause
it cites, and (c) the pixel crop that evidences it.  Those three together are
what the legal notice PDF renders.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, created_at_col

if TYPE_CHECKING:
    from models.inspection_session import InspectionSession


class Violation(Base):
    __tablename__ = "violations"
    __table_args__ = (
        Index("idx_violation_rule", "rule_id"),
        Index("idx_violation_clause", "legal_clause"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("inspection_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rule_id: Mapped[str] = mapped_column(String(50), nullable=False)
    rule_name: Mapped[str | None] = mapped_column(String(100))
    field_name: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    evidence_text: Mapped[str | None] = mapped_column(Text)
    legal_clause: Mapped[str | None] = mapped_column(String(100))
    severity: Mapped[str | None] = mapped_column(String(20))  # CRITICAL | MAJOR | MINOR
    confidence: Mapped[float | None] = mapped_column(Float)
    evidence_crop_path: Mapped[str | None] = mapped_column(String(255))

    # --- deterministic maths behind the finding ---
    calculated_value: Mapped[str | None] = mapped_column(Text)
    expected_value: Mapped[str | None] = mapped_column(Text)
    discrepancy: Mapped[str | None] = mapped_column(Text)
    suggested_fix: Mapped[str | None] = mapped_column(Text)
    penalty_amount: Mapped[float | None] = mapped_column(Float)

    created_at: Mapped[datetime] = created_at_col()

    session: Mapped["InspectionSession"] = relationship(back_populates="violations")
