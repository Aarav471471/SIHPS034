"""Celery application -- the production task fleet from the spec.

Four logical workers consume six queues over the Redis event bus:

  WORKER 1  inspection_pipeline   multi-surface AI inspection & grounding
  WORKER 2  anomaly_radar_queue   price-gouging radar
  WORKER 3  ecom_crawler_queue    e-commerce listing cross-check
  WORKER 4  cross_agency_sync     inter-agency graph & risk routing
            pdf_generation_queue  notice / certificate rendering
            notification_dispatch consumer alerts

Only imported when TASK_BACKEND=celery, so a dev machine never needs Redis.
"""
from __future__ import annotations

from celery import Celery
from kombu import Queue

from app.config import settings
from core.task_runner import (
    QUEUE_AGENCY,
    QUEUE_ECOM,
    QUEUE_INSPECTION,
    QUEUE_NOTIFY,
    QUEUE_PDF,
    QUEUE_RADAR,
)

celery_app = Celery(
    "metrix",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "tasks.pipeline_tasks",
        "tasks.radar_tasks",
        "tasks.ecom_tasks",
        "tasks.pdf_tasks",
        "tasks.agency_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,                 # redeliver if a worker dies mid-inspection
    worker_prefetch_multiplier=1,        # long CPU-bound tasks: no greedy prefetch
    task_reject_on_worker_lost=True,
    result_expires=60 * 60 * 24,
    task_default_queue=QUEUE_INSPECTION,
    task_queues=(
        Queue(QUEUE_INSPECTION),
        Queue(QUEUE_RADAR),
        Queue(QUEUE_ECOM),
        Queue(QUEUE_PDF),
        Queue(QUEUE_NOTIFY),
        Queue(QUEUE_AGENCY),
    ),
    # Vision calls are slow; give the pipeline real headroom before it is killed.
    task_soft_time_limit=600,
    task_time_limit=900,
)

# Periodic work (celery beat)
celery_app.conf.beat_schedule = {
    "price-radar-sweep": {
        "task": "radar.sweep_anomalies",
        "schedule": 900.0,  # every 15 minutes
        "options": {"queue": QUEUE_RADAR},
    },
    "ecom-crosscheck-sweep": {
        "task": "ecom.sweep_listings",
        "schedule": 3600.0 * 6,  # every 6 hours
        "options": {"queue": QUEUE_ECOM},
    },
    "agency-graph-sync": {
        "task": "agency.sync_graph",
        "schedule": 3600.0 * 12,
        "options": {"queue": QUEUE_AGENCY},
    },
    "expiry-alert-dispatch": {
        "task": "notify.scan_expiring_products",
        "schedule": 3600.0 * 24,
        "options": {"queue": QUEUE_NOTIFY},
    },
}


def register_all() -> None:
    """Bridge plain @task functions into Celery under the same names.

    Keeps one source of truth: a task is written once as a normal function and
    both runners dispatch it by the identical name.
    """
    from core.task_runner import registry

    import tasks  # noqa: F401 - side-effect: registers every task

    for name in registry.names():
        fn, queue = registry.get(name)
        celery_app.task(name=name, queue=queue)(fn)
