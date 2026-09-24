"""Declarative base + shared column helpers.

JSONB is used on PostgreSQL and transparently degrades to JSON on SQLite so the
spec's JSONB columns (jurisdiction_geojson, transformation_matrix,
counter_evidence_urls) work in both modes.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, MetaData
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, mapped_column
from sqlalchemy.types import JSON, TypeDecorator


class UTCDateTime(TypeDecorator):
    """A timestamp that is always timezone-aware UTC in Python.

    SQLite has no timezone storage, so a ``DateTime(timezone=True)`` column
    round-trips as a NAIVE datetime there while PostgreSQL returns an aware one.
    Any comparison against ``datetime.now(timezone.utc)`` therefore works in
    production and raises ``TypeError`` in development, or vice versa -- a
    difference that surfaces as a crash in whichever environment was tested
    less.

    Normalising in the type rather than at each call site means application
    code never has to know which database it is talking to, and a new query
    cannot reintroduce the bug by forgetting to convert.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        # A naive value from application code is UTC by this project's
        # convention; anything else is converted rather than assumed.
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

# Portable JSONB: real JSONB on Postgres, plain JSON elsewhere.
JSONVariant = JSON().with_variant(JSONB(), "postgresql")

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    """Normalise a database timestamp to timezone-aware UTC.

    SQLite has no timezone storage, so it returns naive datetimes even from a
    ``DateTime(timezone=True)`` column, while PostgreSQL returns aware ones.
    Subtracting one from ``datetime.now(timezone.utc)`` therefore raises on
    SQLite and works on Postgres -- a difference that would otherwise surface
    as a production-only or dev-only crash. Values stored by this application
    are always UTC, so attaching the timezone is correct rather than a guess.
    """
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def age_days(value: datetime | None, now: datetime | None = None) -> int | None:
    """Whole days between a stored timestamp and now, timezone-safe."""
    aware = as_utc(value)
    if aware is None:
        return None
    return ((now or utcnow()) - aware).days


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    def as_dict(self) -> dict:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        pk = getattr(self, "id", None)
        return f"<{self.__class__.__name__} id={pk}>"


def created_at_col():
    return mapped_column(UTCDateTime, default=utcnow, nullable=False)


def updated_at_col():
    return mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )
