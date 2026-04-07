"""
Shared fixtures for the gokart-factory test suite.

Key design decisions:
- Uses a single in-memory SQLite database with StaticPool so all connections
  share the same underlying database within a test session.
- Patches app.main.engine and app.main.SessionLocal before TestClient fires
  the startup event (which calls Base.metadata.create_all and seed_inventory).
- Patches app.database.SessionLocal so the get_db dependency uses the same
  test database.
- Drops and recreates tables for each test function for clean isolation.
"""
import os

# Must be set before any app module is imported, because auth.py reads
# SECRET_KEY at module load time via os.environ["SECRET_KEY"].
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["ADMIN_KEY"] = "test-admin-key"

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
import app.main as _main_module
import app.database as _db_module

from fastapi.testclient import TestClient


class _AuthClient:
    """Thin wrapper around TestClient that auto-attaches Bearer token headers."""

    def __init__(self, client: TestClient, token: str) -> None:
        self._c = client
        self.token = token
        self._h = {"Authorization": f"Bearer {token}"}

    def get(self, url: str, **kw):
        kw.setdefault("headers", self._h)
        return self._c.get(url, **kw)

    def post(self, url: str, **kw):
        kw.setdefault("headers", self._h)
        return self._c.post(url, **kw)


# ---------------------------------------------------------------------------
# Session-scoped engine: created once, shared across all tests.
# StaticPool is required — without it each sqlite:///:memory: connection gets
# its own empty database, so the second connection sees no tables.
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def test_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Patch module-level references so startup() uses the test engine.
    # main.py does `from .database import engine, SessionLocal` which creates
    # local names in main's namespace — we must patch those directly.
    _main_module.engine = engine
    _main_module.SessionLocal = TestSessionLocal
    # Also patch database module so get_db() uses the test sessionmaker.
    _db_module.SessionLocal = TestSessionLocal

    yield engine, TestSessionLocal

    Base.metadata.drop_all(bind=engine)


# ---------------------------------------------------------------------------
# Function-scoped db_session: fresh tables for every test.
# ---------------------------------------------------------------------------
@pytest.fixture
def db_session(test_engine):
    engine, TestSessionLocal = test_engine

    # Clean slate for this test
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    # Keep module patches in sync (they were set in test_engine but could
    # theoretically drift if another fixture swaps them)
    _main_module.SessionLocal = TestSessionLocal
    _db_module.SessionLocal = TestSessionLocal

    # Seed inventory here so service tests (which don't create a TestClient
    # and therefore never fire the startup event) have the expected baseline.
    # For route tests the startup fires too, but seed_inventory is idempotent.
    from app.services import seed_inventory
    _seed_db = TestSessionLocal()
    seed_inventory(_seed_db)
    _seed_db.close()

    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestSessionLocal
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Unauthenticated TestClient (for /api/init, /api/inventory, /api/admin/flush)
# ---------------------------------------------------------------------------
@pytest.fixture
def client(db_session):
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ---------------------------------------------------------------------------
# Authenticated client — calls /api/init and wraps the client with
# auto-injected Authorization headers.
# ---------------------------------------------------------------------------
@pytest.fixture
def auth_client(client):
    resp = client.post("/api/init")
    assert resp.status_code == 200, resp.json()
    token = resp.json()["token"]
    return _AuthClient(client, token)


# ---------------------------------------------------------------------------
# Standard work order payload helpers
# ---------------------------------------------------------------------------
@pytest.fixture
def std_payload():
    return {
        "frame_type": "Standard",
        "motor_type": "Standard Motor",
        "battery": "Standard",
        "finish": "Black Powder Coat",
    }


@pytest.fixture
def reinforced_payload():
    return {
        "frame_type": "Reinforced Off-Road",
        "motor_type": "Standard Motor",
        "battery": "Standard",
        "finish": "Black Powder Coat",
    }


@pytest.fixture
def high_torque_payload():
    return {
        "frame_type": "Standard",
        "motor_type": "High Torque Motor",
        "battery": "Standard",
        "finish": "Black Powder Coat",
    }
