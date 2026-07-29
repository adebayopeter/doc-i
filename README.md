# Doc-I — Document Intelligence Platform

AI-powered document processing API for Nigerian financial workflows.
Combines Azure Document Intelligence for OCR with Claude AI for
zero-shot classification and field extraction.

## What it does

- **Processes** — define document checklists (e.g. RSA Mortgage requires
  NIN slip, bank statement, offer letter)
- **Submissions** — open a case for an applicant under a process
- **Documents** — upload PDFs/images; the worker classifies them against
  the checklist and extracts structured fields
- **Analysis** — unified record merging fields across documents,
  validation rules, and a routing decision (auto / review / manual)
- **Config** — manage validation rules, confidence thresholds, and
  document categories

## Stack

| Layer | Technology |
|---|---|
| API | FastAPI + Python 3.12 |
| Database | PostgreSQL 16 |
| Queue | Celery + Redis |
| Storage | MinIO (S3-compatible) |
| AI — OCR | Azure Document Intelligence (optional) |
| AI — Classification & Extraction | Claude (Anthropic) |
| Demo | Streamlit |

## Quick start

### Prerequisites

- Docker + Docker Compose
- An Anthropic API key

### 1. Clone and configure

```bash
git clone https://github.com/adebayopeter/doc-i.git
cd doc-i
cp .env.example .env
```

Edit `.env` — the minimum required changes:

```bash
SECRET_KEY=<generate with: python -c "import secrets; print(secrets.token_hex(32))">
ANTHROPIC_API_KEY=sk-ant-...
```

### 2. Start all services

```bash
docker compose up -d --build
```

Six services start: `api`, `worker`, `demo`, `postgres`, `redis`, `minio`.

### 3. Run first-time setup

```bash
make setup
```

This creates the MinIO bucket and seeds the default Nigerian
validation rules (NIN, BVN, NUBAN format checks, age validation,
document expiry, cross-document name consistency).

### 4. Open the interfaces

| Interface | URL |
|---|---|
| Streamlit demo | http://localhost:8502 |
| Swagger UI | http://localhost:8012/docs |
| ReDoc | http://localhost:8012/redoc |
| MinIO console | http://localhost:9001 |

---

## API overview

All endpoints return the standard envelope:

```json
{
  "success": true,
  "message": "Request successful",
  "data": {}
}
```

Authentication: pass your API key as `X-API-Key` in every request.

### API Key Management

The platform supports two types of authentication:

1. **Master SECRET_KEY** (from `.env`) — full admin access, can manage API keys
2. **Per-process API keys** (from database) — scoped to specific processes

#### Creating API keys

Use the master SECRET_KEY or an admin API key to create scoped keys:

```bash
curl -X POST http://localhost:8012/v1/admin/keys \
  -H "X-API-Key: your-secret-key" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Benefits Application - Production",
    "process_ids": ["proc_abc123"],
    "scopes": ["read", "write"]
  }'
```

The full key is returned **only once** — save it immediately.

#### Key types

| Type | `process_ids` | Access |
|---|---|---|
| Admin key | `[]` (empty) | All processes + admin endpoints |
| Scoped key | `["proc_abc"]` | Only listed processes |

#### Admin endpoints

```
POST   /v1/admin/keys           — create a key (returns full key once)
GET    /v1/admin/keys           — list all keys (prefix only)
GET    /v1/admin/keys/{id}      — get key details
PATCH  /v1/admin/keys/{id}      — update name/scope/active
POST   /v1/admin/keys/{id}/rotate — generate new secret
DELETE /v1/admin/keys/{id}      — permanently revoke
```

### Endpoints

```
GET  /health

POST   /v1/processes
GET    /v1/processes
GET    /v1/processes/{id}
DELETE /v1/processes/{id}

POST   /v1/submissions
GET    /v1/submissions
GET    /v1/submissions/{id}
GET    /v1/submissions/{id}/documents
PATCH  /v1/submissions/{id}/status

POST   /v1/documents/submissions/{id}/upload
GET    /v1/documents/{id}
DELETE /v1/documents/{id}

GET /v1/analysis/submissions/{id}/record
GET /v1/analysis/submissions/{id}/validation
GET /v1/analysis/submissions/{id}/decision

GET    /v1/config/rules
GET    /v1/config/rules/{id}
PATCH  /v1/config/rules/{id}
GET    /v1/config/thresholds
PUT    /v1/config/thresholds

POST   /v1/config/categories
GET    /v1/config/categories
GET    /v1/config/categories/{id}
PATCH  /v1/config/categories/{id}
DELETE /v1/config/categories/{id}

# Admin — API Key Management (admin keys only)
POST   /v1/admin/keys
GET    /v1/admin/keys
GET    /v1/admin/keys/{id}
PATCH  /v1/admin/keys/{id}
POST   /v1/admin/keys/{id}/rotate
DELETE /v1/admin/keys/{id}
```

---

## Development workflow

### Run pre-commit checks

```bash
./pre-commit.sh
```

Runs: Black → isort → flake8 → alembic check → pytest (≥ 80% coverage).

### Run tests only

```bash
docker compose exec api pytest --cov
```

### Create a migration

```bash
docker compose exec api alembic revision --autogenerate -m "description"
docker compose exec api alembic upgrade head
```

### Seed validation rules

```bash
make seed          # idempotent — safe to run multiple times
make seed-reset    # drop and re-seed all default rules
```

### Makefile targets

```bash
make dev           # start all services
make stop          # stop all services
make reset         # stop + remove volumes (full reset)
make migrate       # run pending migrations
make seed          # seed default validation rules
make seed-reset    # reset and re-seed rules
make bucket        # create MinIO documents bucket
make setup         # bucket + migrate + seed (first-time init)
```

---

## Project structure

```
doc-i/
├── .env.example              # configuration template
├── .gitignore
├── docker-compose.yml        # 6 services
├── Makefile
├── pre-commit.sh             # Black → isort → flake8 → alembic → pytest
├── api/
│   ├── Dockerfile
│   ├── pyproject.toml        # Black, isort, pytest-cov config
│   ├── main.py               # FastAPI app, custom OpenAPI, all routers
│   ├── requirements/
│   │   ├── base.txt
│   │   ├── local.txt
│   │   └── prod.txt
│   ├── alembic/              # database migrations
│   ├── config/
│   │   ├── settings/         # base, local, prod settings
│   │   ├── logging.py
│   │   └── dependencies.py   # get_db, verify_api_key
│   ├── db/
│   │   ├── session.py
│   │   └── models.py         # 7 tables
│   ├── routers/              # processes, submissions, documents,
│   │   │                     # analysis, config, categories
│   ├── schemas/              # Pydantic v2 schemas
│   ├── services/             # storage, ocr, extraction,
│   │   │                     # aggregation, validation, decisioning
│   ├── workers/
│   │   └── tasks.py          # Celery document processing task
│   ├── scripts/
│   │   ├── seed_rules.py
│   │   └── create_minio_bucket.py
│   └── tests/                # 350+ tests, ~91% coverage
└── demo/
    ├── Dockerfile
    ├── requirements.txt
    └── app.py                # Streamlit 5-page demo
```

---

## Configuration reference

See `.env.example` for all variables with descriptions.

Key variables:

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | Yes | API key — min 16 chars dev, 32 prod |
| `ANTHROPIC_API_KEY` | Yes | Claude API key |
| `CLAUDE_MODEL` | Yes | e.g. `claude-sonnet-4-20250514` |
| `CLAUDE_MAX_TOKENS` | Yes | e.g. `1500` |
| `AZURE_DOCINT_ENDPOINT` | No | Falls back to vision mode if not set |
| `AZURE_DOCINT_KEY` | No | As above |

---

## Validation rules (default)

Seeded by `make setup` — all Nigerian-specific:

| Rule | Type | Field |
|---|---|---|
| Full Name required | required | Full Name |
| Date of Birth required | required | Date of Birth |
| NIN required | required | NIN |
| BVN required | required | BVN |
| Account Number required | required | Account Number |
| NIN format (11 digits) | format | NIN |
| BVN format (11 digits) | format | BVN |
| NUBAN format (10 digits) | format | Account Number |
| Date of Birth not in future | logical | Date of Birth |
| Applicant minimum age 18 | logical | Date of Birth |
| Document not expired | logical | Expiry Date |
| Name consistent across documents | cross_doc | Full Name |

All rules can be enabled/disabled and severity changed via the API
or the Config page in the demo.

---

## Routing decision logic

After classification the analysis endpoints compute a routing decision
per field and an overall submission verdict:

| Confidence | Decision |
|---|---|
| ≥ `auto_above` (default 85%) | auto — process without review |
| between thresholds | review — flag for human review |
| < `manual_below` (default 60%) | manual — requires manual data entry |

Any validation failure or cross-document conflict escalates the
overall decision toward review or manual regardless of confidence.

Thresholds are configurable at runtime via `PUT /v1/config/thresholds`
or the Config page.

---

## Production checklist

- [ ] Set `ENVIRONMENT=production` in `.env`
- [ ] Set `SECRET_KEY` to a 32+ character random string
- [ ] Set `REQUIREMENTS_FILE=requirements/prod.txt`
- [ ] Configure real PostgreSQL credentials
- [ ] Configure real MinIO / S3 credentials
- [ ] Set `AZURE_DOCINT_ENDPOINT` and `AZURE_DOCINT_KEY`
- [ ] Set `ANTHROPIC_API_KEY`
- [ ] Set `ALLOWED_ORIGINS` to your actual frontend domain(s)
- [ ] Remove `--reload` from the API command in `docker-compose.yml`
- [ ] Set up log aggregation (the API logs structured JSON)
- [ ] Run `make setup` on first deploy
- [ ] Create per-process API keys for each application (Benefits, Mortgage, KYC)
- [ ] Rotate the master SECRET_KEY after creating admin API keys