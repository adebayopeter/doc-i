import requests

from constants import API_BASE, HEADERS


# ── API helpers ────────────────────────────────────────────────────────────
def api_get(path: str) -> dict:
    """GET request to the API — returns parsed JSON."""
    try:
        response = requests.get(f"{API_BASE}{path}", headers=HEADERS, timeout=10)
        return response.json()
    except Exception as e:
        return {"success": False, "message": str(e), "data": None}


def api_post(path: str, json: dict = None, files: dict = None) -> dict:
    """POST request — handles both JSON and multipart."""
    try:
        headers = {k: v for k, v in HEADERS.items() if k != "Content-Type"}
        if files:
            response = requests.post(
                f"{API_BASE}{path}",
                headers=headers,
                files=files,
                timeout=30,
            )
        else:
            response = requests.post(
                f"{API_BASE}{path}",
                headers=headers,
                json=json,
                timeout=10,
            )
        return response.json()
    except Exception as e:
        return {"success": False, "message": str(e), "data": None}


def api_patch(path: str, params: dict = None) -> dict:
    """PATCH request."""
    try:
        response = requests.patch(
            f"{API_BASE}{path}",
            headers=HEADERS,
            params=params,
            timeout=10,
        )
        return response.json()
    except Exception as e:
        return {"success": False, "message": str(e), "data": None}


def api_delete(path: str) -> dict:
    """DELETE request."""
    try:
        response = requests.delete(
            f"{API_BASE}{path}", headers=HEADERS, timeout=10
        )
        return response.json()
    except Exception as e:
        return {"success": False, "message": str(e), "data": None}


def api_put(path: str, json: dict = None) -> dict:
    """PUT request."""
    try:
        response = requests.put(
            f"{API_BASE}{path}",
            headers=HEADERS,
            json=json,
            timeout=10,
        )
        return response.json()
    except Exception as e:
        return {"success": False, "message": str(e), "data": None}


def check_api_health() -> bool:
    """Returns True if the API is reachable."""
    try:
        response = requests.get(f"{API_BASE}/health", timeout=5)
        return response.status_code == 200
    except Exception:
        return False


def get_categories() -> list:
    """
    Fetches active categories from the API.
    Returns a list of name strings for use in dropdowns.
    """
    category = api_get("/v1/config/categories")
    if category.get("success"):
        return [c["name"] for c in category["data"].get("items", [])]
    return []
