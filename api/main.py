from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import JSONResponse

from config.logging import get_logger
from config.settings import settings
from routers import documents, processes, submissions

logger = get_logger(__name__)

# App
app = FastAPI(
    title="Doc-I API",
    description=(
        "## Document Intelligence Platform\n\n"
        "AI-powered OCR, document classification, and field extraction API "
        "built for AccessARM Pension's document processing workflows.\n\n"
        "### Standard response format\n"
        "Every endpoint returns:\n"
        "```json\n"
        '{"success": true, "message": "Request successful", "data": {}}\n'
        "```\n\n"
        "### Authentication\n"
        "Pass your API key in every request header:\n"
        "```\nX-API-Key: your-api-key\n```"
    ),
    version="1.0.0",
    contact={
        "name": "Document Intelligence Platform",
        "email": "support@yourfirm.ng",
    },
    license_info={
        "name": "Private — internal use only",
    },
    docs_url=None,
    redoc_url=None,
    openapi_url="/openapi.json",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Custom Swagger UI ──────────────────────────────────────────────────────
@app.get("/docs", include_in_schema=False)
async def swagger_ui():
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="Document Intelligence API — Swagger UI",
        swagger_js_url="https://unpkg.com/swagger-ui-dist@5.9.0/swagger-ui-bundle.js",
        swagger_css_url="https://unpkg.com/swagger-ui-dist@5.9.0/swagger-ui.css",
    )


# ── Custom ReDoc ───────────────────────────────────────────────────────────
@app.get("/redoc", include_in_schema=False)
async def redoc_ui():
    return get_redoc_html(
        openapi_url="/openapi.json",
        title="Document Intelligence API — ReDoc",
        redoc_js_url="https://unpkg.com/redoc@2.1.3/bundles/redoc.standalone.js",
    )


# ── Exception handlers ─────────────────────────────────────────────────────
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """
    Ensures ALL error responses follow the standard envelope:
    {"success": false, "message": "...", "data": null}

    When routers raise HTTPException(detail=error_response(...)),
    FastAPI would normally wrap it as {"detail": {...}}.
    This handler unwraps it so the envelope is always at the top level.
    """
    detail = exc.detail

    # If detail is already our envelope dict — return it directly
    if isinstance(detail, dict) and "success" in detail:
        return JSONResponse(status_code=exc.status_code, content=detail)

    # Otherwise wrap the plain string detail in our envelope
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": str(detail) if detail else "An error occurred",
            "data": None,
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all for unhandled exceptions."""
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": "An unexpected error occurred",
            "data": None,
        },
    )


# ── Routers ────────────────────────────────────────────────────────────────
app.include_router(
    processes.router,
    prefix="/v1/processes",
    tags=["Processes"],
)
app.include_router(
    submissions.router,
    prefix="/v1/submissions",
    tags=["Submissions"],
)
app.include_router(
    documents.router,
    prefix="/v1/documents",
    tags=["Documents"],
)


# ── Health ─────────────────────────────────────────────────────────────────
@app.get(
    "/health",
    tags=["Health"],
    summary="Health check",
    description="Returns API status. No authentication required.",
    response_description="API is running",
)
async def health():
    return {
        "success": True,
        "message": "API is running",
        "data": {
            "status": "ok",
            "version": "1.0.0",
            "environment": settings.ENVIRONMENT,
        },
    }
