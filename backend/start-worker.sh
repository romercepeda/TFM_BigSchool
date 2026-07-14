#!/bin/sh
# Minimal Redis footprint for Upstash free tier:
#   --pool=solo          run tasks in the main process (no forked subprocesses,
#                        no extra broker connections per worker child)
#   --concurrency=1      single task slot (redundant with solo but explicit)
#   --without-heartbeat  no periodic heartbeat commands to Redis
#   --without-gossip     no worker-state broadcast events via Redis pubsub
#   --without-mingle     no startup sync with peer workers
exec celery -A app.worker:celery_app worker --loglevel=info \
    --pool=solo \
    --concurrency=1 \
    --without-heartbeat \
    --without-gossip \
    --without-mingle
