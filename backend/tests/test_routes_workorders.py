"""Tests for work order creation and listing endpoints."""
from app.models import InventoryItem


def test_create_workorder_returns_200(auth_client, std_payload):
    resp = auth_client.post("/api/workorders", json=std_payload)
    assert resp.status_code == 200
    body = resp.json()
    assert "id" in body
    assert body["status"] == "open"
    assert body["created_day"] == 1


def test_create_standard_wo_generates_seven_ops(auth_client, std_payload):
    auth_client.post("/api/workorders", json=std_payload)
    ops = auth_client.get("/api/operations").json()
    assert len(ops) == 7


def test_create_reinforced_wo_generates_eight_ops(auth_client, db_session, reinforced_payload):
    db = db_session()
    db.query(InventoryItem).filter_by(name="Reinforced Off-Road").update({"qty_on_hand": 5})
    db.commit()
    db.close()

    auth_client.post("/api/workorders", json=reinforced_payload)
    ops = auth_client.get("/api/operations").json()
    assert len(ops) == 8
    assert any(op["name"] == "Frame Stress Test" for op in ops)


def test_create_wo_with_out_of_stock_part_generates_backorder_sequence(auth_client):
    # Competition battery has qty=0 in seed data
    payload = {
        "frame_type": "Standard",
        "motor_type": "Standard Motor",
        "battery": "Competition",
        "finish": "Black Powder Coat",
    }
    resp = auth_client.post("/api/workorders", json=payload)
    assert resp.status_code == 200

    ops = auth_client.get("/api/operations").json()
    names = [op["name"] for op in ops]
    assert names[0] == "Backorder Parts"
    assert names[1] == "Receive Parts"


def test_create_wo_rejects_unknown_frame_type(auth_client):
    resp = auth_client.post("/api/workorders", json={
        "frame_type": "Phantom Frame",
        "motor_type": "Standard Motor",
        "battery": "Standard",
        "finish": "Black Powder Coat",
    })
    assert resp.status_code == 422


def test_create_wo_rejects_deprecated_item(auth_client, db_session):
    db = db_session()
    db.query(InventoryItem).filter_by(name="Standard", category="frame").update({"deprecated": True})
    db.commit()
    db.close()

    resp = auth_client.post("/api/workorders", json={
        "frame_type": "Standard",
        "motor_type": "Standard Motor",
        "battery": "Standard",
        "finish": "Black Powder Coat",
    })
    assert resp.status_code == 422


def test_create_wo_decrements_inventory(auth_client, db_session, std_payload):
    db = db_session()
    before = db.query(InventoryItem).filter_by(name="Standard", category="frame").first().qty_on_hand
    db.close()

    auth_client.post("/api/workorders", json=std_payload)

    db = db_session()
    after = db.query(InventoryItem).filter_by(name="Standard", category="frame").first().qty_on_hand
    db.close()
    assert after == before - 1


def test_create_wo_does_not_decrement_infinite_finish(auth_client, db_session, std_payload):
    auth_client.post("/api/workorders", json=std_payload)
    db = db_session()
    finish = db.query(InventoryItem).filter_by(name="Black Powder Coat").first()
    db.close()
    assert finish.qty_on_hand is None


def test_list_workorders_empty_initially(auth_client):
    resp = auth_client.get("/api/workorders")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_workorders_returns_created_wos(auth_client, std_payload):
    auth_client.post("/api/workorders", json=std_payload)
    auth_client.post("/api/workorders", json=std_payload)
    resp = auth_client.get("/api/workorders")
    assert len(resp.json()) == 2


def test_seventh_standard_wo_triggers_backorder(auth_client, std_payload):
    # Standard frame starts at qty=6 — creating 6 WOs drains it to 0,
    # the 7th should insert a Backorder Parts op.
    for _ in range(6):
        auth_client.post("/api/workorders", json=std_payload)
    auth_client.post("/api/workorders", json=std_payload)

    ops = auth_client.get("/api/operations").json()
    wo_ids = {op["work_order_id"] for op in ops}
    last_wo_id = max(wo_ids)
    last_wo_ops = [op["name"] for op in ops if op["work_order_id"] == last_wo_id]
    assert "Backorder Parts" in last_wo_ops
