"""consumer_alerts -- spec section 4.

Push notices for recalls, expired batches and price surges, addressed to
consumers who scanned or saved the affected barcode.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, created_at_col

if TYPE_CHECKING:
    from models.user import User


class ConsumerAlert(Base):
    __tablename__ = "consumer_alerts"
    __table_args__ = (Index("idx_alert_user_read", "user_id", "is_read"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    barcode: Mapped[str | None] = mapped_column(String(50), index=True)
    alert_type: Mapped[str] = mapped_column(String(30), nullable=False)
    severity: Mapped[str | None] = mapped_column(String(20))  # INFO | WARNING | CRITICAL

    title: Mapped[str] = mapped_column(String(150), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    action_url: Mapped[str | None] = mapped_column(String(255))

    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = created_at_col()

    user: Mapped["User | None"] = relationship(back_populates="alerts")
