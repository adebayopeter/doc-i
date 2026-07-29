# Doc-I Production Readiness Audit

**Audit Date:** 2026-07-21
**Auditor:** Claude Opus 4.5
**Codebase Version:** `36b6eda` (main branch)
**Verdict:** **NOT READY** for external developer access

---

## Executive Summary

This audit assesses the Doc-I document intelligence platform for production readiness before exposing the API to external developers. The codebase demonstrates solid engineering fundamentals with ~91% test coverage, consistent API design, and proper error handling. However, **three critical blockers** must be addressed before any external developer access:

1. **No per-developer API keys** — single shared SECRET_KEY means no isolation, no scopes, no usage tracking
2. **No multi-tenancy** — all processes and submissions are globally visible to any API key holder
3. **No rate limiting** — a single bad actor could exhaust Claude/Azure API credits or DoS the system

---

## 1. Security

### Authentication: X-API-Key with Single Shared SECRET_KEY

| Status | Finding |
|--------|---------|
| **🔴 BLOCKER** | Authentication is a single shared `SECRET_KEY` from `.env` |

**Location:** `api/config/dependencies.py:38-64`

```python
async def verify_api_key(api_key: str = api_key_security):
    """
    MVP: validates against a single key from .env
    Production: look up key in the database, check scopes
    """
    if api_key != settings.SECRET_KEY:
        ...
```

**Impact:**
- Every external developer shares the same API key
- No scoped access (read-only vs read-write, process-specific access)
- No way to revoke one developer's access without rotating everyone's key
- No per-developer usage tracking or audit trail

**Recommendation:** Implement an `api_keys` table with:
- `id`, `key_hash`, `developer_id`, `scopes`, `rate_limit`, `created_at`, `expires_at`, `is_active`
- Scopes: `processes:read`, `processes:write`, `submissions:*`, `config:*`, etc.

---

### Hardcoded Secrets

| Status | Finding |
|--------|---------|
| **✅ READY** | No hardcoded secrets in tracked files |

**Verification:**
- `.env` is in `.gitignore`
- Only `.env.example` is tracked (contains placeholder values)
- Grep for `api_key|password|secret|token` in `*.py` shows only test fixtures

---

### CORS Configuration

| Status | Finding |
|--------|---------|
| **⚠️ NEEDS WORK** | CORS is configurable but production validation could be tighter |

**Location:** `api/main.py:59-65`

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Location:** `api/config/settings/prod.py:40-57`

The production settings validator correctly rejects non-HTTPS origins:
```python
if not origin.startswith("https://"):
    raise ValueError(f"All production origins must use HTTPS. Got: {origin}")
```

**However:** `allow_methods=["*"]` and `allow_headers=["*"]` should be restricted to only methods/headers actually used.

**Recommendation:**
```python
allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "HEAD", "OPTIONS"],
allow_headers=["X-API-Key", "Content-Type", "Accept"],
```

---

### SQL Injection

| Status | Finding |
|--------|---------|
| **✅ READY** | Using SQLAlchemy ORM throughout — no raw SQL queries |

**Verification:** Grep for `execute|text\(|raw|select.*from` shows only:
- `raw_ocr_text` field name (not a query)
- `raw` resource type for Cloudinary (not a query)

All database operations use SQLAlchemy query builder:
```python
# Example from api/routers/submissions.py:111-118
submission = (
    db.query(Submission)
    .options(joinedload(Submission.process).joinedload(Process.documents))
    .filter(Submission.id == submission_id)
    .first()
)
```

---

### Rate Limiting

| Status | Finding |
|--------|---------|
| **🔴 BLOCKER** | No rate limiting implemented |

**Verification:** Grep for `rate.?limit|RateLimit|slowapi|throttl` returns no matches.

**Impact:**
- A single developer (or attacker) can exhaust Claude API credits ($$$)
- No protection against runaway scripts uploading thousands of documents
- DoS risk for all platform users

**Recommendation:** Use [slowapi](https://github.com/laurentS/slowapi):
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.post("/submissions/{id}/upload")
@limiter.limit("10/minute")  # Per-key limits after API key lookup
async def upload_document(...):
```

Suggested limits:
- Document upload: 10/minute per key, 100/hour per key
- List endpoints: 100/minute per key
- Analysis endpoints: 50/minute per key

---

### Error Response Information Leakage

| Status | Finding |
|--------|---------|
| **✅ READY** | Stack traces and internal details are not exposed |

**Location:** `api/main.py:169-180`

```python
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all for unhandled exceptions."""
    logger.error(f"Unhandled error: {exc}", exc_info=True)  # Logged server-side
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": "An unexpected error occurred",  # Generic to client
            "data": None,
        },
    )
```

Stack traces are logged server-side but clients receive only generic messages.

---

### Input Validation

| Status | Finding |
|--------|---------|
| **✅ READY** | All endpoints use Pydantic v2 for input validation |

**Examples:**
- `api/schemas/process.py` — ProcessCreate, ProcessUpdate
- `api/schemas/submission.py` — SubmissionCreate
- `api/routers/documents.py:322-342` — File type and size validation

```python
ALLOWED_MIME_TYPES = {"application/pdf", "image/png", "image/jpeg", ...}
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024

if mime_type not in ALLOWED_MIME_TYPES:
    raise HTTPException(status_code=400, detail=error_response(...))
```

---

## 2. API Design and Documentation

### OpenAPI Documentation Quality

| Status | Finding |
|--------|---------|
| **✅ READY** | Every endpoint has summary, description, and response examples |

**Example:** `api/routers/documents.py:234-302`

Each endpoint includes:
- `summary="Upload a document"`
- `description=(multiline markdown with format details)`
- `responses={202: {...example...}, 400: {...examples...}}`

The OpenAPI spec at `/openapi.json` is comprehensive.

---

### Response Envelope Consistency

| Status | Finding |
|--------|---------|
| **✅ READY** | All responses follow `{success, message, data}` pattern |

**Location:** `api/schemas/base.py`

```python
def success_response(data: Any, message: str = "Request successful") -> dict:
    return {"success": True, "message": message, "data": data}

def error_response(message: str, data: Any = None) -> dict:
    return {"success": False, "message": message, "data": data}
```

Custom exception handler at `api/main.py:142-166` ensures even errors follow this envelope.

---

### HTTP Status Codes

| Status | Finding |
|--------|---------|
| **✅ READY** | Status codes used correctly |

| Operation | Status | Example |
|-----------|--------|---------|
| Create | 201 | `POST /v1/processes` |
| Read | 200 | `GET /v1/submissions/{id}` |
| Update | 200 | `PATCH /v1/config/rules/{id}` |
| Delete | 200 | `DELETE /v1/documents/{id}` |
| Async accept | 202 | `POST /v1/documents/submissions/{id}/upload` |
| Not found | 404 | Any resource lookup |
| Validation error | 422 | Invalid transitions, duplicate names |
| Unauthorized | 401 | Missing/invalid API key |

---

### Pagination on List Endpoints

| Status | Finding |
|--------|---------|
| **🔴 BLOCKER** | No pagination on any list endpoint |

**Affected endpoints:**
- `GET /v1/processes` — `api/routers/processes.py:354-373`
- `GET /v1/submissions` — `api/routers/submissions.py:341-363`
- `GET /v1/submissions/{id}/documents` — `api/routers/submissions.py:489-530`
- `GET /v1/config/rules` — `api/routers/config.py`
- `GET /v1/config/categories` — `api/routers/categories.py`

**Current behavior:**
```python
submissions = query.order_by(Submission.created_at.desc()).all()  # Loads everything
```

**Impact:**
- With 10,000 submissions, response could be 10+ MB
- Memory exhaustion risk on API server
- Slow response times, timeouts

**Recommendation:** Add `limit` and `offset` query parameters:
```python
@router.get("")
def list_submissions(
    process_id: Optional[str] = None,
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = db_dependency,
):
    query = db.query(Submission).options(...)
    total = query.count()
    items = query.order_by(...).offset(offset).limit(limit).all()
    return success_response(data={
        "items": [...],
        "total": total,
        "limit": limit,
        "offset": offset,
    })
```

---

### Undocumented or Orphaned Endpoints

| Status | Finding |
|--------|---------|
| **✅ READY** | All endpoints are documented and in use |

All routers are registered in `api/main.py:183-224`.

---

## 3. Multi-Tenancy Readiness

### Data Isolation

| Status | Finding |
|--------|---------|
| **🔴 BLOCKER** | No tenant isolation — all data globally visible |

**Current state:**
- `Process` table has no `tenant_id` or `organization_id`
- `Submission` table has no `tenant_id` or `organization_id`
- Any API key holder can see/modify all processes and submissions

**Location:** `api/db/models.py`

```python
class Process(Base):
    __tablename__ = "processes"
    id = Column(String, primary_key=True, ...)
    name = Column(String(200), nullable=False)
    # NO tenant_id!
```

**Impact:**
- Developer A can read/modify Developer B's processes
- No way to bill by tenant
- No way to enforce data residency requirements

**Recommendation:**

1. Add `organizations` table:
```python
class Organization(Base):
    __tablename__ = "organizations"
    id = Column(String, primary_key=True, default=lambda: _gen_id("org"))
    name = Column(String(200), nullable=False)
    # ... billing info, limits, etc.
```

2. Add `organization_id` foreign key to `Process`, `Submission`, `ValidationRule`, `ProcessThreshold`

3. Filter all queries by the authenticated key's organization:
```python
async def verify_api_key(api_key: str = ...):
    key_record = db.query(APIKey).filter(APIKey.key_hash == hash(api_key)).first()
    return {"key_id": key_record.id, "org_id": key_record.organization_id}

def list_processes(db: Session, auth: dict = Depends(verify_api_key)):
    query = db.query(Process).filter(Process.organization_id == auth["org_id"])
```

---

## 4. Reliability

### Celery Worker Error Handling

| Status | Finding |
|--------|---------|
| **✅ READY** | Proper retries with exponential backoff |

**Location:** `api/workers/tasks.py:30-35`

```python
@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,  # 30 seconds between retries
    ...
)
def process_document(self, document_id, submission_id, file_bytes_b64):
```

**On permanent failure:** `api/workers/tasks.py:212-232`

```python
if self.request.retries >= self.max_retries:
    doc.status = "failed"
    doc.flags = [{"type": "err", "message": f"Classification failed..."}]
    db.commit()
```

---

### External API Failure Handling

| Status | Finding |
|--------|---------|
| **✅ READY** | Azure OCR and Claude failures trigger retries |

**Azure OCR:** `api/services/ocr.py:23-37`
```python
def extract_text(file_bytes, mime_type):
    if not (settings.AZURE_DOCINT_ENDPOINT and settings.AZURE_DOCINT_KEY):
        return ""  # Graceful fallback to vision mode
```

**Claude API:** Failures in `classify_and_extract()` bubble up to the Celery task which retries.

---

### Database Transactions

| Status | Finding |
|--------|---------|
| **✅ READY** | Proper commit/rollback patterns |

**Location:** `api/workers/tasks.py:236-237`
```python
finally:
    db.close()
```

All router functions use the `get_db()` dependency which handles session cleanup:
```python
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()  # Implicit rollback if no commit
```

---

### Bare except: Clauses

| Status | Finding |
|--------|---------|
| **✅ READY** | No bare `except:` clauses found |

All exception handlers catch specific types:
```python
except Exception as e:  # Always typed
    logger.error(f"...")
```

---

## 5. Observability

### Structured Logging

| Status | Finding |
|--------|---------|
| **⚠️ NEEDS WORK** | Logging is plain text, not structured JSON |

**Location:** `api/config/logging.py:26-31`

```python
handler.setFormatter(
    logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
)
```

**Output:** `2026-07-21 10:15:30 | INFO     | routers.submissions | Listed 42 submissions`

**README claims:** "Set up log aggregation (the API logs structured JSON)" — **this is incorrect**.

**Recommendation:** Use `python-json-logger`:
```python
from pythonjsonlogger import jsonlogger

handler.setFormatter(jsonlogger.JsonFormatter(
    '%(asctime)s %(levelname)s %(name)s %(message)s'
))
```

**Output:** `{"asctime": "2026-07-21 10:15:30", "levelname": "INFO", "name": "routers.submissions", "message": "Listed 42 submissions", "submission_count": 42}`

---

### Audit Logging

| Status | Finding |
|--------|---------|
| **⚠️ NEEDS WORK** | AuditLog table exists but is not populated |

**Location:** `api/db/models.py:403-426`

```python
class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, ...)
    submission_id = Column(String, ForeignKey("submissions.id"), ...)
    event = Column(String(100), nullable=False)  # e.g. document.uploaded
    actor = Column(String(200), nullable=True)
    payload = Column(JSON, default=dict, ...)
    created_at = Column(DateTime, ...)
```

**However:** Grep for `AuditLog` shows it's defined but **never written to** in any router or service.

**Recommendation:** Add audit logging to key operations:
```python
# In documents router after upload
db.add(AuditLog(
    submission_id=submission_id,
    event="document.uploaded",
    actor=api_key_id,  # From auth dependency
    payload={"document_id": doc.id, "filename": filename},
))
```

---

### Usage Tracking

| Status | Finding |
|--------|---------|
| **⚠️ NEEDS WORK** | No per-developer usage tracking |

With a single shared API key, there's no way to track:
- How many documents each developer processes
- Which developer triggered a Claude API call
- Billing breakdowns by developer

**Recommendation:** After implementing per-developer API keys:
```python
class APIKeyUsage(Base):
    __tablename__ = "api_key_usage"
    id = Column(Integer, primary_key=True)
    api_key_id = Column(String, ForeignKey("api_keys.id"))
    endpoint = Column(String(100))
    timestamp = Column(DateTime, default=_now)
    claude_tokens_used = Column(Integer, default=0)
```

---

## 6. Testing

### Test Coverage

| Status | Finding |
|--------|---------|
| **✅ READY** | ~91% coverage with 350+ tests |

**Configuration:** `api/pyproject.toml`
```toml
[tool.coverage.report]
fail_under = 80
```

**Exclusions (intentional):**
- `services/extraction.py` — calls Claude API
- `services/ocr.py` — calls Azure API
- `workers/tasks.py` — full Celery integration
- `config/settings/prod.py` — production only

---

### Integration Tests

| Status | Finding |
|--------|---------|
| **✅ READY** | Full upload → classify → analyse flow covered |

**Location:** `api/tests/test_integration.py`

841 lines covering:
1. Process creation with document checklist
2. Submission opening
3. Document upload (2 documents)
4. Classification result injection (simulates Celery)
5. Unified record merging with conflict detection
6. Validation rule execution
7. Routing decision computation
8. Status transitions and terminal state blocking
9. Threshold adjustment effects

---

### New Features Tested

| Status | Finding |
|--------|---------|
| **✅ READY** | Per-document fields and process rules tested |

**Location:** `api/tests/routers/test_extraction_fields.py` (625 lines)

Covers:
- Field summary endpoint
- Add/list/get/update/delete document fields
- Duplicate field name rejection
- Same field name on different documents
- Process-scoped rules creation
- Global vs process rule counts

---

## 7. Data and Configuration

### Database Migrations

| Status | Finding |
|--------|---------|
| **✅ READY** | All migrations have downgrade functions |

**Location:** `api/alembic/versions/`

13 migration files, each with `upgrade()` and `downgrade()`:
```python
def downgrade() -> None:
    op.drop_table('submission_documents')
    op.drop_table('audit_logs')
    ...
```

---

### Seed Script

| Status | Finding |
|--------|---------|
| **✅ READY** | Default Nigerian validation rules seeded |

**Location:** `api/scripts/seed_rules.py`

Seeds:
- NIN format (11 digits)
- BVN format (11 digits)
- NUBAN format (10 digits)
- Min age 18, max age 75
- Document expiry check
- Cross-document name consistency

Idempotent — safe to run multiple times.

---

### Environment Variables

| Status | Finding |
|--------|---------|
| **✅ READY** | `.env.example` is comprehensive |

**Location:** `.env.example` (87 lines)

All required variables documented with:
- Clear section headers
- Comments explaining usage
- Default values where appropriate

---

## 8. Developer Experience

### README / Quickstart

| Status | Finding |
|--------|---------|
| **✅ READY** | README has quickstart guide |

**Location:** `README.md`

Covers:
- Prerequisites
- Clone and configure
- Start services
- First-time setup
- Interface URLs
- Endpoint overview
- Development workflow
- Makefile targets

---

### SDK / Code Examples

| Status | Finding |
|--------|---------|
| **⚠️ NEEDS WORK** | No SDK or code examples provided |

External developers would benefit from:
- Python SDK (`pip install doci-client`)
- JavaScript/TypeScript SDK
- cURL examples in README
- Postman collection

---

### Webhooks

| Status | Finding |
|--------|---------|
| **🔴 BLOCKER** | No webhooks — developers must poll |

**Verification:** Grep for `webhook` returns no matches.

**Current flow:**
1. Developer uploads document
2. Developer polls `GET /v1/documents/{id}` every few seconds
3. Eventually status changes from `processing` to `classified`

**Impact:**
- Inefficient polling wastes API calls
- Developers build polling logic in every integration
- Delayed awareness of completion

**Recommendation:** Add webhook configuration:
```python
class WebhookConfig(Base):
    __tablename__ = "webhook_configs"
    id = Column(String, primary_key=True)
    organization_id = Column(String, ForeignKey("organizations.id"))
    url = Column(String(500))
    events = Column(JSON)  # ["document.classified", "submission.complete"]
    secret = Column(String(100))  # For HMAC signature
```

After classification:
```python
for webhook in org.webhooks:
    if "document.classified" in webhook.events:
        httpx.post(webhook.url, json={...}, headers={"X-Signature": hmac(...)})
```

---

## Summary

### 🔴 BLOCKERS (Must fix before any external access)

| # | Issue | Location | Effort |
|---|-------|----------|--------|
| 1 | Single shared API key — no per-developer keys | `config/dependencies.py:38-64` | Medium |
| 2 | No multi-tenancy — all data globally visible | `db/models.py` (all tables) | High |
| 3 | No rate limiting | All routers | Low |
| 4 | No pagination on list endpoints | `routers/*.py` (list functions) | Low |
| 5 | No webhooks — polling required | N/A (new feature) | Medium |

### ⚠️ NEEDS WORK (Should fix soon after launch)

| # | Issue | Location | Effort |
|---|-------|----------|--------|
| 1 | Logging not structured JSON | `config/logging.py` | Low |
| 2 | AuditLog table not populated | `routers/*.py` | Low |
| 3 | No usage tracking per developer | N/A (requires #1) | Medium |
| 4 | CORS allows all methods/headers | `main.py:63-64` | Low |
| 5 | No SDK or code examples | N/A (new docs) | Medium |

### ✅ NICE TO HAVE (Later improvements)

| # | Issue | Notes |
|---|-------|-------|
| 1 | Postman collection | Export from OpenAPI |
| 2 | Python SDK package | Auto-generate from OpenAPI |
| 3 | TypeScript SDK | Auto-generate from OpenAPI |
| 4 | API versioning strategy | Currently `/v1/` only |
| 5 | OpenTelemetry tracing | For distributed tracing |

---

## Recommended Build Order

Given dependencies between features, implement in this order:

1. **Rate limiting** (1-2 days) — Protects against abuse immediately
2. **Pagination** (1-2 days) — Prevents memory exhaustion on list endpoints
3. **Per-developer API keys** (3-5 days) — Foundation for multi-tenancy
4. **Multi-tenancy** (5-7 days) — Data isolation (depends on #3)
5. **Webhooks** (3-5 days) — Better developer experience
6. **Structured logging + audit logs** (2-3 days) — Observability
7. **Usage tracking** (2-3 days) — Billing preparation (depends on #3)

---

## Final Verdict

**Is this codebase ready to expose to external developers?**

**NO.** The single shared API key and lack of multi-tenancy are fundamental blockers. Any external developer would have full access to all processes and submissions created by any other developer.

**Single most important thing to build next:**

**Per-developer API keys with organization scoping.** This is the foundation for:
- Multi-tenancy (filter by org_id)
- Rate limiting (per-key limits)
- Usage tracking (per-key metrics)
- Webhook configuration (per-org webhooks)
- Billing (per-org invoices)

---

*Generated by Claude Opus 4.5 on 2026-07-21*
