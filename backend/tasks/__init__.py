"""Celery / in-process task modules.

Importing this package registers every @task with the shared registry, which is
what lets one task definition serve both the Celery fleet and the dev runner.
"""
import importlib
import logging

logger = logging.getLogger("metrix.tasks")

for _mod in (
    "pipeline_tasks",
    "radar_tasks",
    "ecom_tasks",
    "pdf_tasks",
    "agency_tasks",
    "notify_tasks",
):
    try:
        importlib.import_module(f"tasks.{_mod}")
    except ModuleNotFoundError:
        logger.debug("tasks.%s not present yet", _mod)
