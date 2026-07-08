"""Celery application — Spec D07 §15.

Broker is Redis (configured via REDIS_URL env var). No result backend is
configured: task status is tracked entirely via the AnalysisJob DB row
(queued/running/completed/failed, polled through GET /ai-reports/jobs) —
nothing in this codebase ever calls AsyncResult or task.get(). A Redis result
backend would open a pubsub subscription per task on send_task() for no
reader; against a connection-limited managed Redis (e.g. Upstash free tier)
those subscriptions get killed by the server and send_task() raises
ConnectionError, turning every upload into a 500. task_ignore_result=True
skips that bookkeeping entirely.

Tasks are auto-discovered from app.worker.tasks at worker startup.

Run the worker:
    celery -A app.worker:celery_app worker --loglevel=info
"""

import os

from celery import Celery

celery_app = Celery(
    "bigschool",
    broker=os.environ.get("REDIS_URL", "redis://redis:6379/0"),
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_ignore_result=True,  # nothing reads task results — see module docstring
    task_acks_late=True,   # acknowledge only after task completes (safer on crash)
    worker_prefetch_multiplier=1,  # one task at a time per worker process
)
