import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config.dependencies import get_db
from db.session import Base
from main import app

# Test database — uses SQLite in memory so no Postgres needed
TEST_DATABASE_URL = "sqlite://"


@pytest.fixture(scope="session")
def test_engine():
    """
    Creates an in-memory SQLite database for the test session.
    StaticPool ensures the same connection is reused across threads.
    """
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session(test_engine):
    """
    Yields a database session for each test.
    Rolls back after each test so tests are isolated.
    """
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=test_engine,
    )
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(scope="function")
def client(db_session):
    """
    FastAPI test client with the test DB injected.
    Overrides the real get_db dependency with the test session.
    """

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def api_key_headers():
    """
    Returns headers with a valid API key for authenticated requests.
    """
    return {"X-API-Key": "dev-secret-change-this-before-production"}
