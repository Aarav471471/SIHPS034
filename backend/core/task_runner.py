"""Task dispatch abstraction -- Celery/Redis in production, threads in dev.

The spec routes work through a Redis event bus into four Celery workers.  That
is exactly what ships in docker-compose.  But a hackathon demo must also run on
a laptop with no Redis, so every task is registered here once and dispatched
through whichever runner TASK_BACKEND selects.

Task functions themselves stay plain callables -- they know nothing about
Celery, which also makes them directly unit-testable.
"""
from __future__ import annotations

import logging
import threading
import traceback
import uuid
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.config import settings

logger = logging.getLogger("metrix.tasks")

# Queue names from the spec's Redis event bus section
QUEUE_INSPECTION = "inspection_pipeline"
QUEUE_RADAR = "anomaly_radar_queue"
QUEUE_ECOM = "ecom_crawler_queue"
QUEUE_PDF = "pdf_generation_queue"
QUEUE_NOTIFY = "notification_dispatch"
QUEUE_AGENCY = "cross_agency_sync"


@dataclass
class TaskHandle:
    """Uniform handle over a Celery AsyncResult or an in-process Future."""

    task_id: str
    name: str
    queue: str
    submitted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _future: Future | None = None
    _async_result: Any = None

    @property
    def status(self) -> str:
        if self._async_result is not None:
            return str(self._async_result.state)
        if self._future is None:
            return "UNKNOWN"
        if self._future.running():
            return "PROCESSING"
        if self._future.done():
            return "FAILURE" if self._future.exception() else "SUCCESS"
        return "PENDING"

    def result(self, timeout: float | None = None) -> Any:
        if self._async_result is not None:
            return self._async_result.get(timeout=timeout)
        if self._future is not None:
            return self._future.result(timeout=timeout)
        return None


class TaskRegistry:
    """Name -> callable, so both runners resolve work the same way."""

    def __init__(self) -> None:
        self._tasks: dict[str, tuple[Callable[..., Any], str]] = {}

    def register(self, name: str, fn: Callable[..., Any], queue: str) -> None:
        self._tasks[name] = (fn, queue)

    def get(self, name: str) -> tuple[Callable[..., Any], str]:
        if name not in self._tasks:
            raise KeyError(
                f"Task {name!r} is not registered. Known tasks: {sorted(self._tasks)}"
            )
        return self._tasks[name]

    def names(self) -> list[str]:
        return sorted(self._tasks)


registry = TaskRegistry()


def task(name: str, queue: str = QUEUE_INSPECTION):
    """Decorator registering a plain function as a dispatchable task."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        registry.register(name, fn, queue)
        fn.task_name = name  # type: ignore[attr-defined]
        fn.task_queue = queue  # type: ignore[attr-defined]
        return fn

    return decorator


class InProcessRunner:
    """Bounded thread pool standing in for Celery workers.

    Deliberately small: the pipeline is CPU-heavy (OpenCV) and I/O-heavy
    (vision API), and an unbounded pool on a demo laptop would thrash.
    """

    def __init__(self, max_workers: int = 4) -> None:
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="metrix")
        self._handles: dict[str, TaskHandle] = {}
        self._lock = threading.Lock()

    def dispatch(self, name: str, *args: Any, **kwargs: Any) -> TaskHandle:
        fn, queue = registry.get(name)
        task_id = uuid.uuid4().hex

        def _run() -> Any:
            try:
                return fn(*args, **kwargs)
            except Exception:
                logger.error("Task %s (%s) failed:\n%s", name, task_id, traceback.format_exc())
                raise

        future = self._pool.submit(_run)
        handle = TaskHandle(task_id=task_id, name=name, queue=queue, _future=future)
        with self._lock:
            self._handles[task_id] = handle
        return handle

    def get_handle(self, task_id: str) -> TaskHandle | None:
        with self._lock:
            return self._handles.get(task_id)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=False)


class CeleryRunner:
    """Publishes onto the Redis event bus for the real worker fleet."""

    def __init__(self) -> None:
        from app.celery_app import celery_app

        self.app = celery_app

    def dispatch(self, name: str, *args: Any, **kwargs: Any) -> TaskHandle:
        _fn, queue = registry.get(name)
        async_result = self.app.send_task(name, args=args, kwargs=kwargs, queue=queue)
        return TaskHandle(
            task_id=async_result.id, name=name, queue=queue, _async_result=async_result
        )

    def get_handle(self, task_id: str) -> TaskHandle | None:
        from celery.result import AsyncResult

        return TaskHandle(
            task_id=task_id,
            name="unknown",
            queue="unknown",
            _async_result=AsyncResult(task_id, app=self.app),
        )

    def shutdown(self) -> None:  # workers own their own lifecycle
        return None


_runner: InProcessRunner | CeleryRunner | None = None


def get_runner() -> InProcessRunner | CeleryRunner:
    global _runner
    if _runner is None:
        if settings.TASK_BACKEND == "celery":
            try:
                _runner = CeleryRunner()
                logger.info("Task backend: Celery over %s", settings.REDIS_URL)
            except Exception as exc:  # Redis down -> degrade rather than crash the API
                logger.warning("Celery unavailable (%s); falling back to in-process runner", exc)
                _runner = InProcessRunner()
        else:
            _runner = InProcessRunner()
            logger.info("Task backend: in-process thread pool")
    return _runner


def dispatch(name: str, *args: Any, **kwargs: Any) -> TaskHandle:
    """Fire a registered task. Callers only ever use this."""
    return get_runner().dispatch(name, *args, **kwargs)


def shutdown_runner() -> None:
    global _runner
    if _runner is not None:
        _runner.shutdown()
        _runner = None
