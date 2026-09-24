"""brand_pre_certifications -- spec section 4 / Self-Certification Sandbox (3.F).

A brand uploads label artwork BEFORE printing.  The same rule engine that
enforces in the field runs in advisory mode; a pass issues a cryptographic
Digital Compliance Certificate and a verifiable QR badge token.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, JSONVariant, created_at_col

if TYPE_CHECKING:
    from models.category import Category
    from models.user import User


class BrandPreCert(Base):
    __tablename__ = "brand_pre_certifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cert_ref: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    brand_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    brand_name: Mapped[str | None] = mapped_column(String(100))

    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))

    die_line_file_path: Mapped[str] = mapped_column(String(255), nullable=False)
    sha256_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # Physical carton the artwork will be printed on -- drives font-height maths
    target_pack_width_cm: Mapped[float | None] = mapped_column(Float)
    target_pack_height_cm: Mapped[float | None] = mapped_column(Float)
    target_surface_area_cm2: Mapped[float | None] = mapped_column(Float)

    compliance_score: Mapped[int | None] = mapped_column(Integer)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    findings: Mapped[list[Any] | None] = mapped_column(JSONVariant)

    digital_badge_token: Mapped[str | None] = mapped_column(String(100), unique=True, index=True)
    badge_qr_path: Mapped[str | None] = mapped_column(String(255))
    audit_report_pdf_path: Mapped[str | None] = mapped_column(String(255))

    created_at: Mapped[datetime] = created_at_col()

    brand: Mapped["User | None"] = relationship()
    category: Mapped["Category | None"] = relationship()
