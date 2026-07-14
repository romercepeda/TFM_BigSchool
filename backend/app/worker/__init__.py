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
    task_ignore_result=True,     # nothing reads task results — see module docstring
    task_acks_late=False,        # ack on receipt, not on completion — avoids restore_visible
    worker_prefetch_multiplier=1,  # one task at a time per worker process
    # Upstash free tier: 500K commands/month. These settings keep idle consumption
    # to ~2K commands/day (~60K/month).
    #
    # With task_acks_late=True Celery runs restore_visible on every event-loop tick
    # (~1/s) to detect stale unacked tasks → ~3 Redis cmds/s = 259K cmds/day just
    # while idle. Switching to task_acks_late=False eliminates that entirely.
    # Trade-off: if the worker crashes mid-task the task is lost (not re-queued),
    # but for this TFM the user can simply re-request the analysis.
    worker_heartbeat=300,                  # heartbeat every 5 min (150x less than default 2 s)
    broker_heartbeat=0,                    # disable AMQP-style broker heartbeat (not for Redis)
    worker_send_task_events=False,         # don't publish task-level events to Redis
    task_send_sent_event=False,            # don't publish "sent" event on enqueue
    broker_connection_retry_on_startup=True,  # silence Celery 6.0 deprecation warning
)
