#!/bin/bash
set -e

case "$SERVICE_TYPE" in
  worker)
    echo "Starting Celery worker with health server..."
    # Start a tiny health check HTTP server in the background
    python -c "
    import threading
    from http.server import HTTPServer, BaseHTTPRequestHandler

    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'worker ok')
        def log_message(self, format, *args):
            pass  # suppress access logs

    def run():
        server = HTTPServer(('0.0.0.0', 8080), HealthHandler)
        server.serve_forever()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    print('Health server running on port 8080')
    " &
    # Start Celery worker
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
