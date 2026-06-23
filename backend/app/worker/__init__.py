"""Celery application — Spec D07 §15.

Broker and result backend are both Redis (configured via REDIS_URL env var).
Tasks are auto-discovered from app.worker.tasks at worker startup.

Run the worker:
    celery -A app.worker:celery_app worker --loglevel=info
"""

import os

from celery import Celery

celery_app = Celery(
    "bigschool",
    broker=os.environ.get("REDIS_URL", "redis://redis:6379/0"),
    backend=os.environ.get("REDIS_URL", "redis://redis:6379/0"),
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,   # acknowledge only after task completes (safer on crash)
    worker_prefetch_multiplier=1,  # one task at a time per worker process
)
