from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from config.settings import settings
from config.logging import get_logger

logger = get_logger(__name__)


# Engine
# pool_pre_ping=True means SQLAlchemy tests the connection before using it.
# Prevents "connection closed" errors after postgres restarts.
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,           # max 10 persistent connections
    max_overflow=20,        # up to 20 extra connections under load
    echo=settings.is_development,  # logs all SQL in dev, silent in prod
)

# Session factory
# SessionLocal() creates a new database session.
# Never use this directly — always use the get_db() dependency in routers.
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# Base class
# All SQLAlchemy models inherit from this.
# Import Base in models.py — never import it anywhere else.
Base = declarative_base()


def get_engine():
    """Returns the engine — used by Alembic migrations."""
    return engine
