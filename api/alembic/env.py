import os
import sys
from logging.config import fileConfig

from sqlalchemy import pool

from alembic import context

# ── Make sure api/ is on the path ─────────────────────────────────────────
# Alembic runs from api/alembic/ — we need api/ on sys.path
# so imports like "from db.models import Base" work correctly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Alembic config object ──────────────────────────────────────────────────
config = context.config

# ── Logging ───────────────────────────────────────────────────────────────
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

from db.models import (  # noqa: E402,F401
    AuditLog,
    Process,
    ProcessDocument,
    Submission,
    SubmissionDocument,
    ValidationRule,
)

# ── Import all models so Alembic can detect changes ───────────────────────
# Every model must be imported here — if you add a new model later
# you must add it to this import or Alembic won't detect it
from db.session import Base  # noqa: E402

# ── Target metadata — tells Alembic what our schema should look like ───────
target_metadata = Base.metadata


# ── Get database URL from settings — never hardcoded ──────────────────────
def get_url() -> str:
    """
    Load DATABASE_URL from our settings.
    This means Alembic uses the same URL as the application —
    no risk of running migrations against the wrong database.
    """
    from config.settings import settings

    return settings.DATABASE_URL


# ── Offline migrations ─────────────────────────────────────────────────────
# Generates SQL scripts without connecting to the database.
# Useful for reviewing what will run before applying.
def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,  # detect column type changes
        compare_server_default=True,  # detect default value changes
    )
    with context.begin_transaction():
        context.run_migrations()


# ── Online migrations ──────────────────────────────────────────────────────
# Connects to the database and applies migrations directly.
# This is what runs when you do: alembic upgrade head
def run_migrations_online() -> None:
    from sqlalchemy import create_engine

    url = get_url()
    connectable = create_engine(
        url,
        poolclass=pool.NullPool,  # no connection pooling during migrations
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


# ── Entry point ────────────────────────────────────────────────────────────
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
