"""session_images -- spec section 4.

Every uploaded surface carries a SHA-256 evidence seal (UNIQUE, so the same
photograph can never be submitted twice) plus the geometric transformation that
was applied during preprocessing.  The stored matrix is what lets the pipeline
map a rectified bounding box back onto original-camera pixels for the legal
notice crops.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, JSONVariant, created_at_col
from models.enums import SurfaceType

if TYPE_CHECKING:
    from models.inspection_session import InspectionSession


class SessionImage(Base):
    __tablename__ = "session_images"
    __table_args__ = (Index("idx_image_hash", "sha256_hash"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("inspection_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    surface_type: Mapped[str] = mapped_column(
        String(20), default=SurfaceType.FRONT, nullable=False
    )
    image_path: Mapped[str] = mapped_column(String(255), nullable=False)
    processed_path: Mapped[str | None] = mapped_column(String(255))
    sha256_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    perceptual_hash: Mapped[str | None] = mapped_column(String(32), index=True)

    image_width_px: Mapped[int | None] = mapped_column(Integer)
    image_height_px: Mapped[int | None] = mapped_column(Integer)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer)

    # --- preprocessing outcome (spec preprocessing/contour.py) ---
    is_curved_surface: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    curvature_score: Mapped[float | None] = mapped_column(Float)
    unwarp_method: Mapped[str | None] = mapped_column(String(30))  # planar | cylindrical | none
    transformation_matrix: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant)

    # --- physical scale, needed to convert pixel heights to millimetres ---
    px_per_mm: Mapped[float | None] = mapped_column(Float)

    uploaded_at: Mapped[datetime] = created_at_col()

    session: Mapped["InspectionSession"] = relationship(back_populates="images")
