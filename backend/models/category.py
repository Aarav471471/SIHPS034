"""categories -- spec section 4 (Updated)."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, JSONVariant, created_at_col

if TYPE_CHECKING:
    from models.product import Product


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sector: Mapped[str | None] = mapped_column(String(50), index=True)
    icon: Mapped[str | None] = mapped_column(String(50))

    # Which rule modules run for this category (registry keys -- spec rules/registry.py)
    rule_pipeline: Mapped[list[str] | None] = mapped_column(JSONVariant)
    # Festival/seasonal risk multiplier consumed by the routing engine (spec 3.C)
    seasonal_multiplier: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)

    total_inspections: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_compliance_score: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = created_at_col()

    products: Mapped[list["Product"]] = relationship(back_populates="category")
