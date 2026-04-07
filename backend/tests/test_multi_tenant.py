"""Tests verifying that tenant data is fully isolated."""
from fastapi.testclient import TestClient
from app.main import app


def _make_auth_client(raw_client: TestClient):
    """Initialize a new tenant and return (headers, token)."""
    resp = raw_client.post("/api/init")
    assert resp.status_code == 200
    token = resp.json()["token"]
    return {"Authorization": f"Bearer {token}"}, token


def test_two_tenants_have_separate_simulation_states(client):
    h1, _ = _make_auth_client(client)
    h2, _ = _make_auth_client(client)

    state1 = client.get("/api/simulation/state", headers=h1).json()
    state2 = client.get("/api/simulation/state", headers=h2).json()
    # Both start at day 1 but belong to different tenants (different JWT payloads)
    assert state1["current_day"] == 1
    assert state2["current_day"] == 1

    # Advance only tenant 1
    client.post("/api/simulation/advance", json={"days": 3}, headers=h1)
    state1_after = client.get("/api/simulation/state", headers=h1).json()
    state2_after = client.get("/api/simulation/state", headers=h2).json()
    assert state1_after["current_day"] == 4
    assert state2_after["current_day"] == 1  # tenant 2 unaffected


def test_tenant_workorders_not_visible_to_other_tenant(client, std_payload):
    h1, _ = _make_auth_client(client)
    h2, _ = _make_auth_client(client)

    client.post("/api/workorders", json=std_payload, headers=h1)

    wos_t2 = client.get("/api/workorders", headers=h2).json()
    assert wos_t2 == []


def test_tenant_operations_not_visible_to_other_tenant(client, std_payload):
    h1, _ = _make_auth_client(client)
    h2, _ = _make_auth_client(client)

    client.post("/api/workorders", json=std_payload, headers=h1)

    ops_t2 = client.get("/api/operations", headers=h2).json()
    assert ops_t2 == []


def test_tenant_cannot_complete_other_tenants_operation(client, std_payload):
    h1, _ = _make_auth_client(client)
    h2, _ = _make_auth_client(client)

    client.post("/api/workorders", json=std_payload, headers=h1)
    ops_t1 = client.get("/api/operations", headers=h1).json()
    pick_id = next(op["id"] for op in ops_t1 if op["name"] == "Pick Components")

    resp = client.post(f"/api/operations/{pick_id}/complete", headers=h2)
    assert resp.status_code == 404


def test_tenant_workcenter_ops_not_visible_to_other_tenant(client, std_payload):
    h1, _ = _make_auth_client(client)
    h2, _ = _make_auth_client(client)

    client.post("/api/workorders", json=std_payload, headers=h1)

    ops_t2 = client.get("/api/workcenters/Assembly/operations", headers=h2).json()
    assert ops_t2 == []


def test_admin_flush_deletes_all_tenants(client, std_payload, db_session):
    from app.models import WorkOrder, Operation
    h1, _ = _make_auth_client(client)
    h2, _ = _make_auth_client(client)

    client.post("/api/workorders", json=std_payload, headers=h1)
    client.post("/api/workorders", json=std_payload, headers=h2)

    db = db_session()
    assert db.query(WorkOrder).count() == 2
    db.close()

    client.post("/api/admin/flush", headers={"X-Admin-Key": "test-admin-key"})

    db = db_session()
    assert db.query(WorkOrder).count() == 0
    assert db.query(Operation).count() == 0
    db.close()
