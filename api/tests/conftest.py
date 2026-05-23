import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config.dependencies import get_db
from db.session import Base
from main import app

TEST_DATABASE_URL = "sqlite://"


@pytest.fixture(scope="session")
def test_engine():
    """
    Creates an in-memory SQLite database for the entire test session.
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
    Wraps each test in a savepoint (nested transaction).
    Any commit() inside the router becomes a savepoint release —
    the outer transaction is rolled back after each test,
    guaranteeing a clean slate for the next test.
    """
    connection = test_engine.connect()
    transaction = connection.begin()

    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=connection,
    )
    session = TestingSessionLocal()

    # Intercept commit() calls — turn them into savepoint releases
    # so router code that calls db.commit() doesn't permanently write data
    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(session, transaction):
        nonlocal nested
        if not nested.is_active:
            nested = connection.begin_nested()

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture(scope="function")
def client(db_session):
    """
    FastAPI test client with the test DB injected.
    Each test gets a fresh database state due to savepoint rollback.
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
    """Valid API key headers for authenticated requests."""
    return {"X-API-Key": "dev-secret-change-this-before-production"}
