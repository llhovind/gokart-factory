"""Tests for the GET /api/inventory endpoint (no auth required)."""


def test_inventory_returns_200_without_auth(client):
    resp = client.get("/api/inventory")
    assert resp.status_code == 200


def test_inventory_has_four_categories(client):
    body = client.get("/api/inventory").json()
    assert set(body.keys()) == {"frame", "motor", "battery", "finish"}


def test_inventory_has_two_frame_items(client):
    body = client.get("/api/inventory").json()
    assert len(body["frame"]) == 2
    names = {item["name"] for item in body["frame"]}
    assert names == {"Standard", "Reinforced Off-Road"}


def test_inventory_has_two_motor_items(client):
    body = client.get("/api/inventory").json()
    assert len(body["motor"]) == 2


def test_inventory_finish_qty_is_null(client):
    body = client.get("/api/inventory").json()
    for item in body["finish"]:
        assert item["qty_on_hand"] is None


def test_inventory_excludes_deprecated_items(client, db_session):
    from app.models import InventoryItem
    db = db_session()
    db.query(InventoryItem).filter_by(name="Standard", category="frame").update({"deprecated": True})
    db.commit()
    db.close()

    body = client.get("/api/inventory").json()
    frame_names = [item["name"] for item in body["frame"]]
    assert "Standard" not in frame_names


def test_inventory_includes_requires_pre_assembly_test_field(client):
    body = client.get("/api/inventory").json()
    reinforced = next(i for i in body["frame"] if i["name"] == "Reinforced Off-Road")
    standard = next(i for i in body["frame"] if i["name"] == "Standard")
    assert reinforced["requires_pre_assembly_test"] is True
    assert standard["requires_pre_assembly_test"] is False
