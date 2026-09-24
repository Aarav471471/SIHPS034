"""
MetriX central configuration.

Every infrastructure dependency named in the Final Production Architecture
(PostgreSQL, Redis/Celery, MinIO, WeasyPrint, PaddleOCR) has a zero-install
development counterpart selected here.  The application code never branches on
environment -- it talks to an adapter interface and this module decides which
implementation is bound.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---------------------------------------------------------------- app ---
    APP_NAME: str = "MetriX"
    APP_DESCRIPTION: str = (
        "Enterprise 360 Legal Metrology & Consumer Trust Ecosystem - "
        "SIH 2025 PS 26034, Ministry of Consumer Affairs, Food & Public Distribution"
    )
    VERSION: str = "3.0.0"
    ENVIRONMENT: Literal["development", "production", "test"] = "development"
    DEBUG: bool = True
    API_PREFIX: str = "/api"

    # ----------------------------------------------------------- database ---
    # Default is file-backed SQLite so the platform boots with no services.
    # docker-compose overrides this with the async PostgreSQL DSN.
    DATABASE_URL: str = f"sqlite+aiosqlite:///{(PROJECT_ROOT / 'metrix.db').as_posix()}"
    DB_ECHO: bool = False

    # -------------------------------------------------------------- redis ---
    REDIS_URL: str = "redis://localhost:6379/0"

    # ---------------------------------------------------- task execution ----
    # "inprocess" -> asyncio/thread worker inside the API (no Redis needed)
    # "celery"    -> real Celery workers over the Redis event bus (spec path)
    TASK_BACKEND: Literal["inprocess", "celery"] = "inprocess"

    # ------------------------------------------------------------ storage ---
    # "local" -> filesystem under STORAGE_DIR ; "minio" -> S3-compatible bucket
    STORAGE_BACKEND: Literal["local", "minio"] = "local"
    STORAGE_DIR: Path = PROJECT_ROOT / "storage"
    PUBLIC_STORAGE_URL: str = "/storage"

    MINIO_ENDPOINT: str = "http://localhost:9000"
    MINIO_ACCESS_KEY: str = "metrix"
    MINIO_SECRET_KEY: str = "metrix-secret"
    MINIO_BUCKET: str = "metrix-evidence"
    MINIO_SECURE: bool = False

    # ----------------------------------------------------------- security ---
    SECRET_KEY: str = "CHANGE-ME-metrix-dev-secret-key-do-not-use-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12          # 12h field shift
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30                  # offline officer PWA

    # ------------------------------------------------------------- vision ---
    # Primary provider per project decision: Claude Vision. NVIDIA NIM is the
    # option that needs no paid account -- build.nvidia.com issues free
    # credits -- and its endpoint is OpenAI-compatible, so it needs no SDK.
    VISION_PROVIDER: Literal["claude", "gemini", "nvidia", "mock"] = "mock"
    ANTHROPIC_API_KEY: str = ""
    CLAUDE_VISION_MODEL: str = "claude-opus-5"
    GEMINI_API_KEY: str = ""
    GEMINI_VISION_MODEL: str = "gemini-2.5-flash"

    NVIDIA_API_KEY: str = ""
    # The 11B, not the 90B: on the free tier the 90B does not serve at all
    # (measured: 180 s read timeout, repeatedly), while the 11B answers a
    # label in ~2.5 s and reads the printed lines correctly. Check the id on
    # build.nvidia.com before relying on it -- NIM ids are renamed and
    # retired more often than vendor SDK ones.
    NVIDIA_VISION_MODEL: str = "meta/llama-3.2-11b-vision-instruct"
    NVIDIA_BASE_URL: str = "https://integrate.api.nvidia.com/v1"
    # NIM rejects an inline base64 image much above ~180 KB, and asks you to
    # use its asset-upload API instead. Staying under the limit by re-encoding
    # is far simpler than a two-step upload for a single pack photograph.
    NVIDIA_MAX_INLINE_IMAGE_KB: int = 175

    VISION_MAX_RETRIES: int = 2
    VISION_TIMEOUT_SECONDS: int = 90

    # ---------------------------------------------------------------- ocr ---
    # "auto" probes for paddle -> rapidocr -> tesseract -> deterministic verifier
    OCR_ENGINE: Literal["auto", "paddle", "rapidocr", "tesseract", "stub"] = "auto"

    # ---------------------------------------------------------------- pdf ---
    PDF_ENGINE: Literal["auto", "weasyprint", "reportlab"] = "auto"

    # ------------------------------------------------- pipeline thresholds ---
    CONFIDENCE_ACCEPT_THRESHOLD: float = 0.75   # >= auto-accept
    CONFIDENCE_REVIEW_FLOOR: float = 0.60       # 0.60-0.75 -> peer review
    PEER_REVIEW_PENALTY_THRESHOLD: float = 50_000.0
    PHASH_DUPLICATE_DISTANCE: int = 5

    # ------------------------------------------- price-gouging radar (3.A) ---
    RADAR_WINDOW_DAYS: int = 30
    RADAR_TAMPER_MULTIPLIER: float = 1.05
    RADAR_MIN_SAMPLES: int = 3

    # ------------------------------------------ citizen trust score (3.B) ---
    TRUST_SCORE_INITIAL: float = 50.0
    TRUST_SCORE_CONFIRMED_DELTA: float = 10.0
    TRUST_SCORE_SPAM_DELTA: float = -20.0
    TRUST_SCORE_VERIFIED_THRESHOLD: float = 80.0

    # --------------------------------------- predictive risk routing (3.C) ---
    RISK_W_HISTORICAL: float = 0.35
    RISK_W_CITIZEN_LEADS: float = 0.25
    RISK_W_PRICE_ANOMALY: float = 0.25
    RISK_W_SEASONAL: float = 0.15
    ROUTE_DEFAULT_RADIUS_KM: float = 10.0
    ROUTE_MAX_STOPS: int = 5

    # ------------------------------------------------ brand dispute (3.G) ---
    DISPUTE_WINDOW_DAYS: int = 15

    # ------------------------------------------------------------- limits ---
    MAX_UPLOAD_MB: int = 25
    RATE_LIMIT_PER_MINUTE: int = 120
    CITIZEN_REPORT_RATE_LIMIT_PER_HOUR: int = 10

    # ---------------------------------------------------------------- cors ---
    # NoDecode: keep pydantic-settings from JSON-parsing the raw dotenv value so
    # the validator below can accept a plain comma-separated list.
    CORS_ORIGINS: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://localhost:5173",   # web dev server
            "http://localhost:4173",   # web preview
            "http://localhost:8081",   # expo metro
            "http://localhost:19006",  # expo web
        ]
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_origins(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @field_validator("STORAGE_DIR", mode="before")
    @classmethod
    def _coerce_path(cls, v):
        return Path(v) if isinstance(v, str) else v

    # ------------------------------------------------------- derived flags ---
    @property
    def is_postgres(self) -> bool:
        return self.DATABASE_URL.startswith("postgresql")

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")

    @property
    def vision_configured(self) -> bool:
        if self.VISION_PROVIDER == "claude":
            return bool(self.ANTHROPIC_API_KEY)
        if self.VISION_PROVIDER == "gemini":
            return bool(self.GEMINI_API_KEY)
        if self.VISION_PROVIDER == "nvidia":
            return bool(self.NVIDIA_API_KEY)
        return True  # mock is always available

    def ensure_dirs(self) -> None:
        for sub in ("uploads", "crops", "reports", "certs", "dieline", "appeals"):
            (self.STORAGE_DIR / sub).mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s


settings = get_settings()
