"""Liveness / readiness and runtime capability reporting.

/health/capabilities is deliberately verbose: it is the single place a demo
operator can look to see which adapter is bound for each subsystem, which
matters when the same codebase runs on SQLite+threads locally and
Postgres+Celery+MinIO in docker.
"""
from __future__ import annotations

import importlib.util
import platform
import sys

from fastapi import APIRouter
from sqlalchemy import text

from app.config import settings
from app.database import engine
from core.deps import DbSession
from schemas.common import HealthResponse

router = APIRouter(tags=["System"])


def _have(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


@router.get("/health", response_model=HealthResponse)
async def health(db: DbSession) -> HealthResponse:
    checks: dict[str, object] = {}
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "connected"
        db_status = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc.__class__.__name__}"
        db_status = "degraded"

    if settings.TASK_BACKEND == "celery":
        try:
            import redis

            redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2).ping()
            checks["redis"] = "connected"
        except Exception as exc:
            checks["redis"] = f"unreachable: {exc.__class__.__name__}"
            db_status = "degraded"

    return HealthResponse(
        status="ok" if db_status == "ok" else "degraded",
        app=settings.APP_NAME,
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
        database="postgresql" if settings.is_postgres else "sqlite",
        task_backend=settings.TASK_BACKEND,
        storage_backend=settings.STORAGE_BACKEND,
        vision_provider=settings.VISION_PROVIDER,
        vision_configured=settings.vision_configured,
        checks=checks,
    )


@router.get("/health/capabilities")
async def capabilities() -> dict:
    """Which optional subsystems are actually available in this process."""
    return {
        "runtime": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "sqlalchemy_url_driver": engine.url.drivername,
        },
        "vision": {
            "provider": settings.VISION_PROVIDER,
            "configured": settings.vision_configured,
            "anthropic_sdk": _have("anthropic"),
            "google_genai_sdk": _have("google.genai"),
        },
        "computer_vision": {
            "opencv": _have("cv2"),
            "pillow": _have("PIL"),
            "imagehash": _have("imagehash"),
            "pyzbar_barcode": _have("pyzbar"),
        },
        "ocr": {
            "configured": settings.OCR_ENGINE,
            "paddleocr": _have("paddleocr"),
            "rapidocr": _have("rapidocr_onnxruntime"),
            "pytesseract": _have("pytesseract"),
        },
        "geo": {"shapely": _have("shapely")},
        "reporting": {
            "configured": settings.PDF_ENGINE,
            "weasyprint": _have("weasyprint"),
            "reportlab": _have("reportlab"),
            "qrcode": _have("qrcode"),
        },
        "infrastructure": {
            "task_backend": settings.TASK_BACKEND,
            "celery": _have("celery"),
            "redis_client": _have("redis"),
            "storage_backend": settings.STORAGE_BACKEND,
            "boto3_s3": _have("boto3"),
            "asyncpg": _have("asyncpg"),
            "aiosqlite": _have("aiosqlite"),
        },
    }
