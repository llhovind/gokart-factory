"""Tests for authentication and admin endpoints."""
from app.models import Operation, SimulationState, WorkOrder


# ---------------------------------------------------------------------------
# POST /api/init
# ---------------------------------------------------------------------------

def test_init_returns_200_and_token(client):
    resp = client.post("/api/init")
    assert resp.status_code == 200
    body = resp.json()
    assert "token" in body
    assert isinstance(body["token"], str)
    assert len(body["token"]) > 0


def test_init_creates_simulation_state_at_day_one(client, db_session):
    resp = client.post("/api/init")
    token = resp.json()["token"]

    state_resp = client.get(
        "/api/simulation/state",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert state_resp.status_code == 200
    assert state_resp.json()["current_day"] == 1


# ---------------------------------------------------------------------------
# Protected route auth edge cases
# ---------------------------------------------------------------------------

def test_missing_authorization_header_returns_422(client):
    resp = client.get("/api/simulation/state")
    assert resp.status_code == 422


def test_wrong_auth_prefix_returns_401(client):
    resp = client.get(
        "/api/simulation/state",
        headers={"Authorization": "Token not-a-bearer"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid authorization header"


def test_invalid_jwt_returns_401(client):
    resp = client.get(
        "/api/simulation/state",
        headers={"Authorization": "Bearer this.is.garbage"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid or expired token"


def test_valid_token_returns_200(auth_client):
    resp = auth_client.get("/api/simulation/state")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# POST /api/admin/flush
# ---------------------------------------------------------------------------

def test_admin_flush_missing_header_returns_422(client):
    resp = client.post("/api/admin/flush")
    assert resp.status_code == 422


def test_admin_flush_wrong_key_returns_403(client):
    resp = client.post("/api/admin/flush", headers={"X-Admin-Key": "wrong"})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Invalid admin key"


def test_admin_flush_correct_key_returns_200(client):
    resp = client.post("/api/admin/flush", headers={"X-Admin-Key": "test-admin-key"})
    assert resp.status_code == 200
    assert resp.json() == {"flushed": True}


def test_admin_flush_deletes_all_tenant_data(auth_client, client, db_session, std_payload):
    # Create a WO for the authenticated tenant
    auth_client.post("/api/workorders", json=std_payload)

    db = db_session()
    assert db.query(WorkOrder).count() > 0
    assert db.query(Operation).count() > 0
    assert db.query(SimulationState).count() > 0
    db.close()

    client.post("/api/admin/flush", headers={"X-Admin-Key": "test-admin-key"})

    db = db_session()
    assert db.query(WorkOrder).count() == 0
    assert db.query(Operation).count() == 0
    assert db.query(SimulationState).count() == 0
    db.close()


def test_admin_flush_resets_inventory_to_seed_qty(auth_client, client, db_session, std_payload):
    from app.models import InventoryItem
    # Deplete Standard frame by creating WOs
    for _ in range(3):
        auth_client.post("/api/workorders", json=std_payload)

    db = db_session()
    frame_qty = db.query(InventoryItem).filter_by(name="Standard", category="frame").first().qty_on_hand
    assert frame_qty == 3  # started at 6, created 3 WOs
    db.close()

    client.post("/api/admin/flush", headers={"X-Admin-Key": "test-admin-key"})

    db = db_session()
    frame_qty_after = db.query(InventoryItem).filter_by(name="Standard", category="frame").first().qty_on_hand
    assert frame_qty_after == 6  # reset to seed value
    db.close()
