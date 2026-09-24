"""Async SQLAlchemy 2.0 engine / session factory.

Binds to PostgreSQL (asyncpg) or SQLite (aiosqlite) purely from DATABASE_URL,
so the ORM layer written against the spec schema is identical in both modes.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

_engine_kwargs: dict[str, Any] = {
    "echo": settings.DB_ECHO,
    "future": True,
    "pool_pre_ping": True,
}

if settings.is_sqlite:
    # SQLite has no real pooling story for async; keep it simple and serialized.
    _engine_kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
else:
    _engine_kwargs.update(pool_size=20, max_overflow=10, pool_recycle=1800)

engine: AsyncEngine = create_async_engine(settings.DATABASE_URL, **_engine_kwargs)

if settings.is_sqlite:

    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - driver hook
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")      # concurrent reads during writes
        cur.execute("PRAGMA foreign_keys=ON")       # match Postgres FK behaviour
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()


AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a request-scoped session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Create every table declared on Base.metadata (dev / demo bootstrap)."""
    from models import Base  # noqa: F401 - imports all model modules

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_db() -> None:
    from models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def dispose_db() -> None:
    await engine.dispose()
