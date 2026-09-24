"""MetriX API gateway -- spec app/main.py.

FastAPI application factory: CORS, rate limiting, static evidence serving,
router mounting and lifespan management.  Route modules are attached
defensively so a partially-built subsystem never prevents the gateway (and
therefore the demo) from booting.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import dispose_db, init_db

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
# These emit a line per statement at DEBUG and bury everything else.
for _noisy in ("aiosqlite", "asyncio", "multipart", "botocore", "urllib3", "httpcore"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

logger = logging.getLogger("metrix")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("=" * 68)
    logger.info(" %s v%s  |  %s", settings.APP_NAME, settings.VERSION, settings.ENVIRONMENT)
    logger.info(" DB      : %s", "PostgreSQL" if settings.is_postgres else "SQLite")
    logger.info(" Tasks   : %s", settings.TASK_BACKEND)
    logger.info(" Storage : %s", settings.STORAGE_BACKEND)
    logger.info(
        " Vision  : %s (%s)",
        settings.VISION_PROVIDER,
        "configured" if settings.vision_configured else "NO API KEY",
    )
    logger.info("=" * 68)

    # Worker threads publish WebSocket progress onto this loop.
    from core.websocket_manager import bind_loop

    bind_loop(asyncio.get_running_loop())

    settings.ensure_dirs()
    # Dev/demo convenience. Under Postgres, Alembic owns the schema.
    if settings.is_sqlite:
        await init_db()
    yield

    from core.task_runner import shutdown_runner

    shutdown_runner()
    await dispose_db()
    logger.info("MetriX shut down cleanly")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        description=settings.APP_DESCRIPTION,
        version=settings.VERSION,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+)(:\d+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Process-Time", "X-Request-ID"],
    )

    # ---------------------------------------------------------- middleware --
    _hits: dict[str, deque[float]] = defaultdict(deque)

    @app.middleware("http")
    async def rate_limit_and_timing(request: Request, call_next):
        """Sliding-window limiter (spec: 'Rate Limiting & Anti-Spam Shield').

        In-memory by design for single-node dev; behind multiple gateway
        replicas this moves to Redis, which is why the window logic is kept
        trivial and swappable.
        """
        if request.url.path.startswith(settings.API_PREFIX):
            client = request.client.host if request.client else "unknown"
            now = time.monotonic()
            window = _hits[client]
            while window and now - window[0] > 60:
                window.popleft()
            if len(window) >= settings.RATE_LIMIT_PER_MINUTE:
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={"detail": "Rate limit exceeded. Try again shortly."},
                )
            window.append(now)

        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Process-Time"] = f"{(time.perf_counter() - started) * 1000:.1f}ms"
        return response

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": str(exc) if settings.DEBUG else "Internal server error",
                "path": request.url.path,
            },
        )

    # ------------------------------------------------------------- tasks ---
    # Importing the package runs every @task decorator, populating the shared
    # registry. Without this the gateway boots fine and then fails at the first
    # dispatch, so it is done eagerly at construction rather than on demand.
    import tasks  # noqa: F401

    from core.task_runner import registry

    logger.info("Registered tasks: %s", ", ".join(registry.names()) or "none")

    # ------------------------------------------------------------- routers --
    from routes import auth, health

    app.include_router(health.router)
    app.include_router(auth.router, prefix=settings.API_PREFIX)

    # Subsystems land here phase by phase; a module that is not present yet
    # must not take the whole gateway down.
    optional_routers = [
        ("routes.sessions", "/inspections", ["Inspections"]),
        ("routes.consumer", "/consumer", ["Consumer"]),
        ("routes.officer", "/officer", ["Officer Intelligence"]),
        ("routes.brand", "/brand", ["Brand"]),
        ("routes.ecom", "/ecom", ["E-Commerce"]),
        ("routes.policy", "/policy", ["Policy"]),
        ("routes.categories", "/categories", ["Catalogue"]),
        ("routes.products", "/products", ["Catalogue"]),
        ("routes.admin", "/admin", ["Admin"]),
        ("routes.ws", "", ["WebSocket"]),
    ]
    for module_path, _prefix, _tags in optional_routers:
        try:
            module = __import__(module_path, fromlist=["router"])
            app.include_router(module.router, prefix=settings.API_PREFIX)
            logger.debug("Mounted %s", module_path)
        except ModuleNotFoundError:
            logger.debug("Router %s not present yet -- skipping", module_path)
        except Exception:
            logger.exception("Router %s failed to mount", module_path)

    # ------------------------------------------------- evidence static mount --
    if settings.STORAGE_BACKEND == "local":
        app.mount(
            "/storage",
            StaticFiles(directory=str(settings.STORAGE_DIR)),
            name="storage",
        )

    @app.get("/", tags=["System"])
    async def root() -> dict:
        return {
            "name": settings.APP_NAME,
            "tagline": "AI-Powered Legal Metrology Compliance Engine for Packaged Commodities",
            "version": settings.VERSION,
            "problem_statement": "SIH 2025 - PS 26034",
            "ministry": "Ministry of Consumer Affairs, Food & Public Distribution",
            "pillars": [
                "Officer Enforcement Intelligence",
                "Consumer Empowerment & Active Auditing",
                "Brand, Retailer & E-Commerce Collaboration",
                "Policymakers & Inter-Agency Intelligence",
            ],
            "docs": "/docs",
            "health": "/health",
        }

    return app


app = create_app()
