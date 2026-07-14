#!/bin/sh
# --concurrency=1: single process. Default uses os.cpu_count() which in Azure
# reads the host's CPU count (4-8), multiplying all Redis polling by that factor.
exec celery -A app.worker:celery_app worker --loglevel=info --concurrency=1
