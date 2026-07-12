#!/bin/bash
set -e

case "$SERVICE_TYPE" in
  worker)
    echo "Starting health server..."
    python worker_health.py &
    echo "Starting Celery worker..."
    exec celery -A workers.tasks worker --loglevel=info --concurrency=2
    ;;
  api)
    echo "Running database migrations..."
    alembic upgrade head
    echo "Seeding default rules..."
    python scripts/seed_rules.py
    echo "Starting API server..."
    exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8012}
    ;;
  *)
    echo "Running database migrations..."
    alembic upgrade head
    echo "Starting API server..."
    exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8012}
    ;;
esac
