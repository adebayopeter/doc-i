#!/bin/bash
set -e

case "$SERVICE_TYPE" in
  worker)
    echo "Starting Celery worker..."
    exec celery -A workers.tasks worker --loglevel=info --concurrency=2
    ;;
  api)
    echo "Starting API server..."
    exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8012}
    ;;
  *)
    echo "Starting API server (default)..."
    exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8012}
    ;;
esac
