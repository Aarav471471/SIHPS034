"""ecom_listings_crosscheck -- spec section 4 / E-Com Cross-Verification (3.H).

Compares what a platform *lists* against what the physical pack *declares*.
Discrepancies are actionable under Rule 6(10) of the Packaged Commodities Rules
(mandatory declarations on e-commerce listings).
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, created_at_col, UTCDateTime

if TYPE_CHECKING:
    from models.product import Product


class EcomListingCrosscheck(Base):
    __tablename__ = "ecom_listings_crosscheck"
    __table_args__ = (Index("idx_ecom_platform", "platform_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), index=True)
    barcode: Mapped[str | None] = mapped_column(String(50), index=True)
    platform_name: Mapped[str] = mapped_column(String(50), nullable=False)
    listing_url: Mapped[str] = mapped_column(Text, nullable=False)
    listing_title: Mapped[str | None] = mapped_column(String(300))

    scraped_mrp: Mapped[float | None] = mapped_column(Float)
    physical_pack_mrp: Mapped[float | None] = mapped_column(Float)
    mrp_discrepancy: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    country_of_origin_found: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    online_net_qty: Mapped[str | None] = mapped_column(String(50))
    physical_net_qty: Mapped[str | None] = mapped_column(String(50))
    net_qty_discrepancy: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    manufacturer_found: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    customer_care_found: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    is_compliant: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    violation_notes: Mapped[str | None] = mapped_column(Text)
    last_checked_at: Mapped[datetime] = mapped_column(
        UTCDateTime, nullable=True
    )
    created_at: Mapped[datetime] = created_at_col()

    product: Mapped["Product | None"] = relationship(back_populates="ecom_listings")
