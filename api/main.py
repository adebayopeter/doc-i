from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config.logging import get_logger
from config.settings import settings

logger = get_logger(__name__)

# App
app = FastAPI(
    title="Document Intelligence API",
    description="""
    ## Document Intelligence Platform
    
    AI-powered OCR, document classification, and field extraction API
    built for AccessARM Pension's document processing workflows.

    ### Features
    - **Multi-process** — define any document workflow (mortgage, benefits application, onboarding)
    - **AI classification** — Claude classifies any document type with no training
    - **Field extraction** — structured data extracted from every document
    - **Aggregation** — fields merged across all documents with conflict detection
    - **Validation** — configurable rule engine (required, format, logic, cross-doc)
    - **Decisioning** — confidence-based routing: auto / review / manual

    ### Standard response format
    Every endpoint returns:
    ```json
    {
        "success": true,
        "message": "Request successful",
        "data": { ... }
    }
    ```

    ### Authentication
    Pass API key in every request header:
    """,
    version="1.0.0",
    contact={
        "name": "Doc-I Platform",
        "email": "ICT@access-armpensions.com",
    },
    license_info={
        "name": "Private — internal use only",
    },
    docs_url="/docs",  # Swagger UI
    redoc_url="/redoc",  # ReDoc
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


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": "An unexpected error occurred",
            "data": None,
        },
    )


# ── Routers
# Add routers here as I build each one
# from routers import processes, submissions, documents, analysis, config
# app.include_router(processes.router, prefix="/v1/processes", tags=["Processes"])

# Health
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
