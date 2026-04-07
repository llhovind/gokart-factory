"""Tests for simulation state and advancement endpoints."""


def test_get_simulation_state_returns_day_one_after_init(auth_client):
    resp = auth_client.get("/api/simulation/state")
    assert resp.status_code == 200
    assert resp.json()["current_day"] == 1


def test_get_simulation_state_404_when_sim_not_found(client, db_session):
    # Call init to get a valid token, then delete the sim state row
    init_resp = client.post("/api/init")
    token = init_resp.json()["token"]

    db = db_session()
    from app.models import SimulationState
    db.query(SimulationState).delete()
    db.commit()
    db.close()

    resp = client.get(
        "/api/simulation/state",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_advance_default_increments_by_one(auth_client):
    resp = auth_client.post("/api/simulation/advance", json={})
    assert resp.status_code == 200
    assert resp.json()["current_day"] == 2


def test_advance_explicit_days(auth_client):
    resp = auth_client.post("/api/simulation/advance", json={"days": 5})
    assert resp.status_code == 200
    assert resp.json()["current_day"] == 6


def test_advance_next_event_jumps_to_earliest_future_start(auth_client, std_payload):
    # Create a WO so there are ops to jump to.
    # Pick starts at day 1, Frame Assembly at day 2, so next_event from day 1
    # should jump to the first scheduled_start_day > 1.
    auth_client.post("/api/workorders", json=std_payload)

    resp = auth_client.post("/api/simulation/advance", json={"mode": "next_event"})
    assert resp.status_code == 200
    # Jumped to day 2 (Frame Assembly starts at day 2, which is > current_day=1)
    assert resp.json()["current_day"] == 2


def test_advance_next_event_with_no_ops_does_not_move(auth_client):
    # No work orders → no scheduled_start_days → next_event has nothing to jump to
    before = auth_client.get("/api/simulation/state").json()["current_day"]
    resp = auth_client.post("/api/simulation/advance", json={"mode": "next_event"})
    assert resp.status_code == 200
    assert resp.json()["current_day"] == before


def test_advance_triggers_awaiting_completion_transition(auth_client, std_payload):
    # After advancing to day 2, Pick (end_day=2) should become awaiting_completion.
    auth_client.post("/api/workorders", json=std_payload)
    auth_client.post("/api/simulation/advance", json={"days": 1})

    ops_resp = auth_client.get("/api/operations")
    ops = {op["name"]: op for op in ops_resp.json()}
    assert ops["Pick Components"]["status"] == "awaiting_completion"


def test_advance_404_when_no_sim_state(client, db_session):
    init_resp = client.post("/api/init")
    token = init_resp.json()["token"]

    db = db_session()
    from app.models import SimulationState
    db.query(SimulationState).delete()
    db.commit()
    db.close()

    resp = client.post(
        "/api/simulation/advance",
        json={"days": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
