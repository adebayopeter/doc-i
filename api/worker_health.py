"""Tiny HTTP health server for the Celery worker — keeps Render awake."""
from http.server import BaseHTTPRequestHandler, HTTPServer


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"worker ok")

    def log_message(self, format, *args):
        pass  # suppress access logs


if __name__ == "__main__":
    port = 8080
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    print(f"Health server running on port {port}")
    server.serve_forever()
