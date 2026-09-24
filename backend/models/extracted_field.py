"""extracted_fields -- spec section 4.

Each row is one declaration the Vision LLM claimed to see, paired with the
deterministic OCR re-read of the exact same pixel crop.  Keeping both
confidences side by side is what makes the "AI proposes, deterministic code
verifies" guarantee auditable in court.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, created_at_col

if TYPE_CHECKING:
    from models.inspection_session import InspectionSession


class ExtractedField(Base):
    __tablename__ = "extracted_fields"
    __table_args__ = (Index("idx_field_session_name", "session_id", "field_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("inspection_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    detected_value: Mapped[str | None] = mapped_column(Text)
    normalized_value: Mapped[str | None] = mapped_column(Text)
    surface_found: Mapped[str | None] = mapped_column(String(20))

    # --- bounding box in ORIGINAL image pixel space (post inverse-mapping) ---
    bbox_x: Mapped[int | None] = mapped_column(Integer)
    bbox_y: Mapped[int | None] = mapped_column(Integer)
    bbox_width: Mapped[int | None] = mapped_column(Integer)
    bbox_height: Mapped[int | None] = mapped_column(Integer)

    # --- dual confidence (spec extraction/confidence.py) ---
    confidence_vision_llm: Mapped[float | None] = mapped_column(Float)
    confidence_ocr_verify: Mapped[float | None] = mapped_column(Float)
    ocr_agreement: Mapped[bool | None] = mapped_column(Boolean)
    ocr_read_value: Mapped[str | None] = mapped_column(Text)

    raw_pixel_crop_path: Mapped[str | None] = mapped_column(String(255))
    font_height_mm: Mapped[float | None] = mapped_column(Float)
    is_missing: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = created_at_col()

    session: Mapped["InspectionSession"] = relationship(back_populates="fields")

    @property
    def effective_confidence(self) -> float:
        """Fused score. Disagreement between the two readers is penalised hard."""
        v = self.confidence_vision_llm or 0.0
        o = self.confidence_ocr_verify
        if o is None:
            return round(v * 0.85, 4)  # unverified claims never reach full trust
        if self.ocr_agreement is False:
            return round(min(v, o) * 0.5, 4)
        return round((v * 0.6) + (o * 0.4), 4)
