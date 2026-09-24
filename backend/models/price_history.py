"""price_history_scans -- spec section 4 / Price-Gouging Radar (spec 3.A).

Every consumer AND officer scan appends one immutable row here:
`(barcode, printed_mrp, store_gps, timestamp)`.  The radar groups these by
barcode over a sliding window, derives the modal MRP, and flags any retailer
charging more than RADAR_TAMPER_MULTIPLIER times that mode.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, created_at_col

if TYPE_CHECKING:
    from models.user import User


class PriceHistoryScan(Base):
    __tablename__ = "price_history_scans"
    __table_args__ = (
        Index("idx_price_barcode", "barcode"),
        Index("idx_price_time", "scanned_at"),
        Index("idx_price_barcode_time", "barcode", "scanned_at"),
        Index("idx_price_store", "store_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    barcode: Mapped[str] = mapped_column(String(50), nullable=False)
    product_name: Mapped[str | None] = mapped_column(String(200))
    brand_name: Mapped[str | None] = mapped_column(String(100))

    scanned_mrp: Mapped[float] = mapped_column(Float, nullable=False)
    modal_mrp_at_scan: Mapped[float | None] = mapped_column(Float)
    scanned_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    source: Mapped[str | None] = mapped_column(String(20))  # CONSUMER | OFFICER | ECOM

    store_name: Mapped[str | None] = mapped_column(String(150))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)

    is_anomalous: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    anomaly_reason: Mapped[str | None] = mapped_column(Text)
    overcharge_pct: Mapped[float | None] = mapped_column(Float)

    scanned_at: Mapped[datetime] = created_at_col()

    scanned_by: Mapped["User | None"] = relationship()
