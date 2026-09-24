"""cross_agency_links -- spec section 4 / Unified Regulatory Graph (spec 3.I).

Correlates a Legal Metrology offender with its FSSAI licence, BIS/ISI
registration and GSTIN, so repeat packaging fraud can be escalated to the
relevant sister authority instead of dying inside one department.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, created_at_col, UTCDateTime


class CrossAgencyLink(Base):
    __tablename__ = "cross_agency_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    brand_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    legal_entity_name: Mapped[str | None] = mapped_column(String(200))

    fssai_number: Mapped[str | None] = mapped_column(String(20), index=True)
    fssai_valid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    fssai_expiry: Mapped[datetime | None] = mapped_column(UTCDateTime)

    bis_reg_number: Mapped[str | None] = mapped_column(String(50))
    bis_valid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    gstin: Mapped[str | None] = mapped_column(String(20), index=True)
    gstin_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Aggregate risk multiplier fed into the officer routing engine
    risk_index: Mapped[float] = mapped_column(Float, default=0.0, nullable=False, index=True)
    lm_violation_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    escalation_notes: Mapped[str | None] = mapped_column(Text)

    last_synced_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = created_at_col()

    @property
    def flagged_agencies(self) -> list[str]:
        flags = []
        if self.fssai_number and not self.fssai_valid:
            flags.append("FSSAI")
        if self.bis_reg_number and not self.bis_valid:
            flags.append("BIS")
        if self.gstin and not self.gstin_active:
            flags.append("GSTN")
        return flags
