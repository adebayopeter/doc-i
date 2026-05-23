#!/bin/bash
set -e

# ── Colours ────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No colour

echo ""
echo "🔍 Running pre-commit checks for Document Intelligence Platform..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── Check Docker is running ────────────────────────────────────────────────
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}❌ Docker is not running. Start Docker and try again.${NC}"
    exit 1
fi

# ── Check api container is up ──────────────────────────────────────────────
if ! docker compose ps api | grep -q "running"; then
    echo -e "${YELLOW}⚠️  API container not running. Starting services...${NC}"
    docker compose up -d
    sleep 3
fi

# ── Step 1: Black formatting ───────────────────────────────────────────────
echo ""
echo "1️⃣  Formatting code with Black..."
if docker compose exec -T api black . --check --diff; then
    echo -e "${GREEN}   ✅ Black: code is properly formatted${NC}"
else
    echo -e "${YELLOW}   ⚠️  Black found formatting issues. Auto-fixing...${NC}"
    docker compose exec -T api black .
    echo -e "${GREEN}   ✅ Black: formatting applied${NC}"
fi

# ── Step 2: isort import sorting ──────────────────────────────────────────
echo ""
echo "2️⃣  Sorting imports with isort..."
if docker compose exec -T api isort . --check-only --diff; then
    echo -e "${GREEN}   ✅ isort: imports are correctly sorted${NC}"
else
    echo -e "${YELLOW}   ⚠️  isort found unsorted imports. Auto-fixing...${NC}"
    docker compose exec -T api isort .
    echo -e "${GREEN}   ✅ isort: imports sorted${NC}"
fi

# ── Step 3: flake8 linting ────────────────────────────────────────────────
echo ""
echo "3️⃣  Checking linting with flake8..."
if docker compose exec -T api flake8 .; then
    echo -e "${GREEN}   ✅ flake8: no linting issues${NC}"
else
    echo -e "${RED}   ❌ flake8: linting errors found. Fix before committing.${NC}"
    exit 1
fi

# ── Step 4: Alembic migration check ──────────────────────────────────────
echo ""
echo "4️⃣  Checking for missing Alembic migrations..."
if docker compose exec -T api alembic check; then
    echo -e "${GREEN}   ✅ Alembic: all migrations are up to date${NC}"
else
    echo -e "${RED}   ❌ Alembic: detected model changes without a migration.${NC}"
    echo -e "${RED}      Run: docker compose exec api alembic revision --autogenerate -m 'your message'${NC}"
    exit 1
fi

# ── Step 5: Run tests with coverage ──────────────────────────────────────
echo ""
echo "5️⃣  Running tests with coverage..."
if docker compose exec -T api pytest tests/ -v \
    --cov=. \
    --cov-report=term-missing \
    --cov-fail-under=80; then
    echo -e "${GREEN}   ✅ Tests: all passed with coverage ≥ 80%${NC}"
else
    echo -e "${RED}   ❌ Tests failed or coverage below 80%. Fix before committing.${NC}"
    exit 1
fi

# ── All passed ────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${GREEN}✅ All checks passed! Safe to commit.${NC}"
echo ""
