import os

# ── API config ─────────────────────────────────────────────────────────────
API_BASE = os.getenv("API_BASE_URL", "http://api:8012")
API_KEY = os.getenv("SECRET_KEY", "dev-secret-change-this-before-production")

HEADERS = {
    "X-API-Key": API_KEY,
    "Accept": "application/json",
}

# ── Demo password protection ───────────────────────────────────────────────
# If set, the demo requires this password to access. If empty, no password gate.
DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "")

# ── Colours ────────────────────────────────────────────────────────────────
DECISION_COLOUR = {
    "auto": "🟢",
    "review": "🟡",
    "manual": "🔴",
}

STATUS_COLOUR = {
    "open": "⚪",
    "in_progress": "🔵",
    "complete": "🟢",
    "rejected": "🔴",
    "uploaded": "⚪",
    "processing": "🔵",
    "classified": "🟢",
    "failed": "🔴",
}
