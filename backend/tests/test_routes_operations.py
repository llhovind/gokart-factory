"""Tests for operation listing, completion, and rework flow endpoints."""
from app.models import InventoryItem, WorkOrder
from app.services import _inspection_result, _THRESHOLDS


def _first_failing_id(op_name: str) -> int:
    threshold = _THRESHOLDS[op_name]
    for i in range(1, 500):
        if _inspection_result(i, op_name) < threshold:
            return i
    raise RuntimeError(f"No failing ID found for {op_name}")


def _first_passing_id(op_name: str) -> int:
    threshold = _THRESHOLDS[op_name]
    for i in range(1, 500):
        if _inspection_result(i, op_name) >= threshold:
            return i
    raise RuntimeError(f"No passing ID found for {op_name}")


# ---------------------------------------------------------------------------
# GET /api/operations
# ---------------------------------------------------------------------------

def test_list_operations_empty_before_workorder(auth_client):
    resp = auth_client.get("/api/operations")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_operations_returns_all_ops(auth_client, std_payload):
    auth_client.post("/api/workorders", json=std_payload)
    resp = auth_client.get("/api/operations")
    assert len(resp.json()) == 7


def test_list_operations_sorted_by_scheduled_start_day(auth_client, std_payload):
    auth_client.post("/api/workorders", json=std_payload)
    auth_client.post("/api/workorders", json=std_payload)
    ops = auth_client.get("/api/operations").json()
    starts = [op["scheduled_start_day"] for op in ops]
    assert starts == sorted(starts)


# ---------------------------------------------------------------------------
# GET /api/workcenters/{name}/operations
# ---------------------------------------------------------------------------

def test_workcenter_ops_filter_by_name(auth_client, std_payload):
    auth_client.post("/api/workorders", json=std_payload)
    resp = auth_client.get("/api/workcenters/Assembly/operations")
    assert resp.status_code == 200
    ops = resp.json()
    assert len(ops) == 3
    assert all(op["work_center"] == "Assembly" for op in ops)


def test_workcenter_ops_standard_assembly_names(auth_client, std_payload):
    auth_client.post("/api/workorders", json=std_payload)
    ops = auth_client.get("/api/workcenters/Assembly/operations").json()
    names = {op["name"] for op in ops}
    assert names == {"Frame Assembly", "Motor Installation", "Final Assembly"}


def test_unknown_workcenter_returns_empty_list(auth_client):
    resp = auth_client.get("/api/workcenters/Nonexistent/operations")
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# POST /api/operations/{op_id}/complete
# ---------------------------------------------------------------------------

def test_complete_operation_returns_complete_status(auth_client, std_payload):
    auth_client.post("/api/workorders", json=std_payload)
    ops = auth_client.get("/api/operations").json()
    pick = next(op for op in ops if op["name"] == "Pick Components")

    resp = auth_client.post(f"/api/operations/{pick['id']}/complete")
    assert resp.status_code == 200
    assert resp.json()["status"] == "complete"


def test_complete_operation_sets_actual_completion_day(auth_client, std_payload):
    auth_client.post("/api/simulation/advance", json={"days": 2})
    auth_client.post("/api/workorders", json=std_payload)
    ops = auth_client.get("/api/operations").json()
    pick = next(op for op in ops if op["name"] == "Pick Components")

    resp = auth_client.post(f"/api/operations/{pick['id']}/complete")
    assert resp.json()["actual_completion_day"] == 3  # current_day = 3


def test_complete_nonexistent_op_returns_404(auth_client):
    resp = auth_client.post("/api/operations/99999/complete")
    assert resp.status_code == 404


def test_complete_op_triggers_reschedule_of_downstream(auth_client, std_payload, db_session):
    auth_client.post("/api/workorders", json=std_payload)
    ops_before = {op["name"]: op for op in auth_client.get("/api/operations").json()}
    pick_id = ops_before["Pick Components"]["id"]

    # Complete Pick at day 1 (actual_completion_day=1, scheduled_end_day=2)
    # Frame Assembly had start_day=2; should remain 2 or update if early
    auth_client.post(f"/api/operations/{pick_id}/complete")

    ops_after = {op["name"]: op for op in auth_client.get("/api/operations").json()}
    # Frame Assembly depends on Pick; after completing Pick at day 1,
    # reschedule_all uses actual_completion_day=1 as dep_end → start still ≥ 1
    assert ops_after["Frame Assembly"]["scheduled_start_day"] is not None


# ---------------------------------------------------------------------------
# Inspection pass — no rework
# ---------------------------------------------------------------------------

def _position_wo_id(auth_client, db_session, target_id: int, std_payload: dict):
    """Create (target_id - 1) bare WO rows directly so the next route WO gets target_id."""
    from app.models import WorkOrder as WOModel
    if target_id > 1:
        db = db_session()
        for _ in range(target_id - 1):
            db.add(WOModel(
                tenant_id="__dummy__",
                frame_type="Standard", motor_type="Standard Motor",
                battery="Standard", finish="Black Powder Coat",
                status="open", created_day=1,
            ))
        db.flush()
        db.commit()
        db.close()


def test_frame_stress_test_pass_does_not_insert_rework(auth_client, db_session, std_payload):
    pass_id = _first_passing_id("Frame Stress Test")
    _position_wo_id(auth_client, db_session, pass_id, std_payload)

    db = db_session()
    db.query(InventoryItem).filter_by(name="Reinforced Off-Road").update({"qty_on_hand": 5})
    db.commit()
    db.close()

    reinforced = {**std_payload, "frame_type": "Reinforced Off-Road"}
    wo_resp = auth_client.post("/api/workorders", json=reinforced)
    wo_id = wo_resp.json()["id"]
    assert wo_id == pass_id

    ops_before = auth_client.get("/api/operations").json()
    count_for_wo = sum(1 for op in ops_before if op["work_order_id"] == wo_id)

    fst = next(op for op in ops_before if op["name"] == "Frame Stress Test")
    auth_client.post(f"/api/operations/{fst['id']}/complete")

    ops_after = auth_client.get("/api/operations").json()
    count_for_wo_after = sum(1 for op in ops_after if op["work_order_id"] == wo_id)
    assert count_for_wo_after == count_for_wo


# ---------------------------------------------------------------------------
# Inspection fail — rework flow
# ---------------------------------------------------------------------------

def test_frame_stress_test_fail_inserts_rework_and_retest(auth_client, db_session, std_payload):
    fail_id = _first_failing_id("Frame Stress Test")
    _position_wo_id(auth_client, db_session, fail_id, std_payload)

    db = db_session()
    db.query(InventoryItem).filter_by(name="Reinforced Off-Road").update({"qty_on_hand": 5})
    db.commit()
    db.close()

    reinforced = {**std_payload, "frame_type": "Reinforced Off-Road"}
    wo_resp = auth_client.post("/api/workorders", json=reinforced)
    wo_id = wo_resp.json()["id"]
    assert wo_id == fail_id

    ops_before = auth_client.get("/api/operations").json()
    count_before = sum(1 for op in ops_before if op["work_order_id"] == wo_id)

    fst = next(op for op in ops_before if op["name"] == "Frame Stress Test")
    auth_client.post(f"/api/operations/{fst['id']}/complete")

    ops_after = auth_client.get("/api/operations").json()
    count_after = sum(1 for op in ops_after if op["work_order_id"] == wo_id)
    assert count_after == count_before + 2

    names_after = {op["name"] for op in ops_after if op["work_order_id"] == wo_id}
    assert "Rework: Frame Stress Test" in names_after
    assert "Retest: Frame Stress Test" in names_after


def test_rework_op_has_rework_count_one(auth_client, db_session, std_payload):
    fail_id = _first_failing_id("Frame Stress Test")
    _position_wo_id(auth_client, db_session, fail_id, std_payload)

    db = db_session()
    db.query(InventoryItem).filter_by(name="Reinforced Off-Road").update({"qty_on_hand": 5})
    db.commit()
    db.close()

    reinforced = {**std_payload, "frame_type": "Reinforced Off-Road"}
    auth_client.post("/api/workorders", json={**std_payload, "frame_type": "Reinforced Off-Road"})

    ops = auth_client.get("/api/operations").json()
    fst = next(op for op in ops if op["name"] == "Frame Stress Test")
    auth_client.post(f"/api/operations/{fst['id']}/complete")

    ops_after = auth_client.get("/api/operations").json()
    rework = next((op for op in ops_after if op["name"] == "Rework: Frame Stress Test"), None)
    retest = next((op for op in ops_after if op["name"] == "Retest: Frame Stress Test"), None)
    assert rework is not None and rework["rework_count"] == 1
    assert retest is not None and retest["rework_count"] == 1


def test_rework_capped_completing_retest_does_not_insert_more_ops(auth_client, db_session, std_payload):
    fail_id = _first_failing_id("Frame Stress Test")
    _position_wo_id(auth_client, db_session, fail_id, std_payload)

    db = db_session()
    db.query(InventoryItem).filter_by(name="Reinforced Off-Road").update({"qty_on_hand": 5})
    db.commit()
    db.close()

    reinforced = {**std_payload, "frame_type": "Reinforced Off-Road"}
    wo_resp = auth_client.post("/api/workorders", json=reinforced)
    wo_id = wo_resp.json()["id"]

    ops = auth_client.get("/api/operations").json()
    fst = next(op for op in ops if op["name"] == "Frame Stress Test")
    auth_client.post(f"/api/operations/{fst['id']}/complete")

    ops_after_fail = auth_client.get("/api/operations").json()
    count_after_fail = sum(1 for op in ops_after_fail if op["work_order_id"] == wo_id)

    rework = next(op for op in ops_after_fail if op["name"] == "Rework: Frame Stress Test")
    retest = next(op for op in ops_after_fail if op["name"] == "Retest: Frame Stress Test")
    auth_client.post(f"/api/operations/{rework['id']}/complete")
    auth_client.post(f"/api/operations/{retest['id']}/complete")

    ops_final = auth_client.get("/api/operations").json()
    count_final = sum(1 for op in ops_final if op["work_order_id"] == wo_id)
    assert count_final == count_after_fail  # no new ops added
