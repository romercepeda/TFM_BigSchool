#!/bin/sh
set -e
echo "Applying Alembic migrations..."
alembic upgrade head
echo "Migrations applied. Starting server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
