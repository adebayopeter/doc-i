import os

# ── API config ─────────────────────────────────────────────────────────────
API_BASE = os.getenv("API_BASE_URL", "http://api:8012")
API_KEY = os.getenv("SECRET_KEY", "dev-secret-change-this-before-production")

HEADERS = {
    "X-API-Key": API_KEY,
    "Accept": "application/json",
}

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
