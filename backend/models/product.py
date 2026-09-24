"""products -- spec section 4 (Updated)."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, created_at_col, updated_at_col, UTCDateTime

if TYPE_CHECKING:
    from models.category import Category
    from models.ecom_listing import EcomListingCrosscheck


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), index=True)
    brand_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    barcode: Mapped[str | None] = mapped_column(String(50), index=True)
    image_url: Mapped[str | None] = mapped_column(String(255))
    fssai_number: Mapped[str | None] = mapped_column(String(20))

    # Reference declarations -- the "official" values a consumer scan compares against
    official_mrp: Mapped[float | None] = mapped_column(Float)
    net_quantity: Mapped[str | None] = mapped_column(String(50))
    net_quantity_value: Mapped[float | None] = mapped_column(Float)
    net_quantity_unit: Mapped[str | None] = mapped_column(String(10))
    country_of_origin: Mapped[str | None] = mapped_column(String(80))

    avg_score: Mapped[float | None] = mapped_column(Float)
    badge_level: Mapped[str | None] = mapped_column(String(20), index=True)
    total_inspections: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    violation_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_inspected_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    category: Mapped["Category | None"] = relationship(back_populates="products", lazy="joined")
    ecom_listings: Mapped[list["EcomListingCrosscheck"]] = relationship(
        back_populates="product"
    )

    @property
    def unit_price_display(self) -> str | None:
        """Rule 6(2) unit sale price, e.g. '0.0400/g'."""
        if not (self.official_mrp and self.net_quantity_value and self.net_quantity_unit):
            return None
        return f"{self.official_mrp / self.net_quantity_value:.4f}/{self.net_quantity_unit}"
