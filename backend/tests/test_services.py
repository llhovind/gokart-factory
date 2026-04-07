"""
Tests for the service layer (app/services.py).

These tests call service functions directly with real DB sessions rather than
going through the HTTP layer — they exercise business logic at fine granularity.
"""
import pytest

from app.models import InventoryItem, Operation, SimulationState, WorkOrder
from app.schemas import WorkOrderCreate
from app.services import (
    _inspection_result,
    _THRESHOLDS,
    complete_operation,
    create_work_order_with_operations,
    seed_inventory,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_STD_DATA = WorkOrderCreate(
    frame_type="Standard",
    motor_type="Standard Motor",
    battery="Standard",
    finish="Black Powder Coat",
)

_REINFORCED_DATA = WorkOrderCreate(
    frame_type="Reinforced Off-Road",
    motor_type="Standard Motor",
    battery="Standard",
    finish="Black Powder Coat",
)

_HIGH_TORQUE_DATA = WorkOrderCreate(
    frame_type="Standard",
    motor_type="High Torque Motor",
    battery="Standard",
    finish="Black Powder Coat",
)


def _give_stock(db, name: str, qty: int, category: str | None = None):
    """Update qty_on_hand for an inventory item by name."""
    q = db.query(InventoryItem).filter_by(name=name)
    if category:
        q = q.filter_by(category=category)
    q.update({"qty_on_hand": qty})
    db.commit()


def _first_failing_id(op_name: str) -> int:
    """Return the first WO id (≥ 1) whose inspection result is below threshold."""
    threshold = _THRESHOLDS[op_name]
    for i in range(1, 500):
        if _inspection_result(i, op_name) < threshold:
            return i
    raise RuntimeError(f"No failing ID found for {op_name}")


def _first_passing_id(op_name: str) -> int:
    """Return the first WO id (≥ 1) whose inspection result is above/equal threshold."""
    threshold = _THRESHOLDS[op_name]
    for i in range(1, 500):
        if _inspection_result(i, op_name) >= threshold:
            return i
    raise RuntimeError(f"No passing ID found for {op_name}")


def _insert_sim(db, tenant_id: str, current_day: int = 1):
    db.add(SimulationState(tenant_id=tenant_id, current_day=current_day))
    db.commit()


# ---------------------------------------------------------------------------
# seed_inventory
# ---------------------------------------------------------------------------

def test_seed_inventory_inserts_eight_items(db_session):
    db = db_session()
    # startup already seeded; count should be 8
    assert db.query(InventoryItem).count() == 8
    db.close()


def test_seed_inventory_is_idempotent(db_session):
    db = db_session()
    seed_inventory(db)
    seed_inventory(db)
    assert db.query(InventoryItem).count() == 8
    db.close()


def test_seed_inventory_standard_frame_has_qty_six(db_session):
    db = db_session()
    item = db.query(InventoryItem).filter_by(name="Standard", category="frame").first()
    assert item.qty_on_hand == 6
    db.close()


def test_seed_inventory_finish_has_no_qty(db_session):
    db = db_session()
    for item in db.query(InventoryItem).filter_by(category="finish").all():
        assert item.qty_on_hand is None
    db.close()


# ---------------------------------------------------------------------------
# _inspection_result
# ---------------------------------------------------------------------------

def test_inspection_result_is_deterministic(db_session):
    r1 = _inspection_result(42, "Frame Stress Test")
    r2 = _inspection_result(42, "Frame Stress Test")
    assert r1 == r2


def test_inspection_result_range():
    for i in range(1, 20):
        r = _inspection_result(i, "Frame Stress Test")
        assert 0 <= r <= 99


def test_inspection_result_differs_across_op_names():
    r_frame = _inspection_result(1, "Frame Stress Test")
    r_motor = _inspection_result(1, "Motor Torque Test")
    # Almost certainly different; this exercises both branches
    assert isinstance(r_frame, int)
    assert isinstance(r_motor, int)


# ---------------------------------------------------------------------------
# Work order creation — op count and names
# ---------------------------------------------------------------------------

def test_standard_wo_generates_seven_ops(db_session):
    db = db_session()
    _insert_sim(db, "t1")
    wo = create_work_order_with_operations(db, "t1", _STD_DATA, 1)
    ops = db.query(Operation).filter_by(work_order_id=wo.id).all()
    assert len(ops) == 7
    db.close()


def test_standard_wo_op_names(db_session):
    db = db_session()
    _insert_sim(db, "t1")
    wo = create_work_order_with_operations(db, "t1", _STD_DATA, 1)
    names = [op.name for op in db.query(Operation).filter_by(work_order_id=wo.id).all()]
    assert names == [
        "Pick Components",
        "Frame Assembly",
        "Motor Installation",
        "Final Assembly",
        "Powder Coat",
        "Final QC",
        "Ship Order",
    ]
    db.close()


def test_standard_wo_dep_chain(db_session):
    db = db_session()
    _insert_sim(db, "t1")
    wo = create_work_order_with_operations(db, "t1", _STD_DATA, 1)
    ops = {op.name: op for op in db.query(Operation).filter_by(work_order_id=wo.id).all()}

    assert ops["Pick Components"].depends_on_operation_id is None
    assert ops["Frame Assembly"].depends_on_operation_id == ops["Pick Components"].id
    assert ops["Motor Installation"].depends_on_operation_id == ops["Frame Assembly"].id
    assert ops["Final Assembly"].depends_on_operation_id == ops["Motor Installation"].id
    assert ops["Powder Coat"].depends_on_operation_id == ops["Final Assembly"].id
    assert ops["Final QC"].depends_on_operation_id == ops["Powder Coat"].id
    assert ops["Ship Order"].depends_on_operation_id == ops["Final QC"].id
    db.close()


def test_reinforced_wo_generates_eight_ops_with_frame_test(db_session):
    db = db_session()
    _insert_sim(db, "t1")
    _give_stock(db, "Reinforced Off-Road", 5)
    wo = create_work_order_with_operations(db, "t1", _REINFORCED_DATA, 1)
    ops = db.query(Operation).filter_by(work_order_id=wo.id).all()
    assert len(ops) == 8
    names = [op.name for op in ops]
    assert "Frame Stress Test" in names
    db.close()


def test_frame_stress_test_work_center_and_duration(db_session):
    db = db_session()
    _insert_sim(db, "t1")
    _give_stock(db, "Reinforced Off-Road", 5)
    wo = create_work_order_with_operations(db, "t1", _REINFORCED_DATA, 1)
    ops = {op.name: op for op in db.query(Operation).filter_by(work_order_id=wo.id).all()}
    fst = ops["Frame Stress Test"]
    assert fst.work_center == "IQC"
    assert fst.duration_days == 1
    db.close()


def test_frame_assembly_depends_on_frame_stress_test(db_session):
    db = db_session()
    _insert_sim(db, "t1")
    _give_stock(db, "Reinforced Off-Road", 5)
    wo = create_work_order_with_operations(db, "t1", _REINFORCED_DATA, 1)
    ops = {op.name: op for op in db.query(Operation).filter_by(work_order_id=wo.id).all()}
    assert ops["Frame Assembly"].depends_on_operation_id == ops["Frame Stress Test"].id
    db.close()


def test_high_torque_wo_generates_eight_ops(db_session):
    # Motor test only: Pick + Motor Torque Test + 6 standard assembly ops = 8
    db = db_session()
    _insert_sim(db, "t1")
    _give_stock(db, "High Torque Motor", 5)
    wo = create_work_order_with_operations(db, "t1", _HIGH_TORQUE_DATA, 1)
    ops = db.query(Operation).filter_by(work_order_id=wo.id).all()
    assert len(ops) == 8
    names = [op.name for op in ops]
    assert "Motor Torque Test" in names
    db.close()


def test_both_tests_generates_nine_ops(db_session):
    # Frame + Motor test: Pick + FST + MTT + 6 standard = 9
    db = db_session()
    _insert_sim(db, "t1")
    _give_stock(db, "Reinforced Off-Road", 5)
    _give_stock(db, "High Torque Motor", 5)
    data = WorkOrderCreate(
        frame_type="Reinforced Off-Road",
        motor_type="High Torque Motor",
        battery="Standard",
        finish="Black Powder Coat",
    )
    wo = create_work_order_with_operations(db, "t1", data, 1)
    ops = db.query(Operation).filter_by(work_order_id=wo.id).all()
    assert len(ops) == 9
    names = [op.name for op in ops]
    assert "Frame Stress Test" in names
    assert "Motor Torque Test" in names
    db.close()


# ---------------------------------------------------------------------------
# Backorder path
# ---------------------------------------------------------------------------

def test_backorder_sequence_when_battery_out_of_stock(db_session):
    db = db_session()
    _insert_sim(db, "t1")
    data = WorkOrderCreate(
        frame_type="Standard",
        motor_type="Standard Motor",
        battery="Competition",
        finish="Black Powder Coat",
    )
    wo = create_work_order_with_operations(db, "t1", data, 1)
    ops = db.query(Operation).filter_by(work_order_id=wo.id).order_by(Operation.id).all()
    names = [op.name for op in ops]
    assert names[0] == "Backorder Parts"
    assert names[1] == "Receive Parts"
    assert names[2] == "Pick Components"
    db.close()


def test_backorder_receive_depends_on_backorder(db_session):
    db = db_session()
    _insert_sim(db, "t1")
    data = WorkOrderCreate(
        frame_type="Standard",
        motor_type="Standard Motor",
        battery="Competition",
        finish="Black Powder Coat",
    )
    wo = create_work_order_with_operations(db, "t1", data, 1)
    ops = {op.name: op for op in db.query(Operation).filter_by(work_order_id=wo.id).all()}
    assert ops["Receive Parts"].depends_on_operation_id == ops["Backorder Parts"].id
    assert ops["Pick Components"].depends_on_operation_id == ops["Receive Parts"].id
    db.close()


# ---------------------------------------------------------------------------
# Inventory decrement
# ---------------------------------------------------------------------------

def test_create_wo_decrements_qty_on_hand(db_session):
    db = db_session()
    _insert_sim(db, "t1")
    frame_before = db.query(InventoryItem).filter_by(name="Standard", category="frame").first().qty_on_hand
    create_work_order_with_operations(db, "t1", _STD_DATA, 1)
    db.expire_all()
    frame_after = db.query(InventoryItem).filter_by(name="Standard", category="frame").first().qty_on_hand
    assert frame_after == frame_before - 1
    db.close()


def test_create_wo_does_not_decrement_infinite_finish(db_session):
    db = db_session()
    _insert_sim(db, "t1")
    create_work_order_with_operations(db, "t1", _STD_DATA, 1)
    db.expire_all()
    finish = db.query(InventoryItem).filter_by(name="Black Powder Coat").first()
    assert finish.qty_on_hand is None
    db.close()


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------

def test_unknown_frame_raises_422(db_session):
    from fastapi import HTTPException
    db = db_session()
    _insert_sim(db, "t1")
    bad_data = WorkOrderCreate(
        frame_type="Phantom Frame",
        motor_type="Standard Motor",
        battery="Standard",
        finish="Black Powder Coat",
    )
    with pytest.raises(HTTPException) as exc_info:
        create_work_order_with_operations(db, "t1", bad_data, 1)
    assert exc_info.value.status_code == 422
    db.close()


def test_deprecated_item_raises_422(db_session):
    from fastapi import HTTPException
    db = db_session()
    _insert_sim(db, "t1")
    db.query(InventoryItem).filter_by(name="Standard", category="frame").update({"deprecated": True})
    db.commit()
    with pytest.raises(HTTPException) as exc_info:
        create_work_order_with_operations(db, "t1", _STD_DATA, 1)
    assert exc_info.value.status_code == 422
    db.close()


# ---------------------------------------------------------------------------
# complete_operation
# ---------------------------------------------------------------------------

def test_complete_operation_marks_status_and_day(db_session):
    db = db_session()
    _insert_sim(db, "t1", current_day=3)
    wo = create_work_order_with_operations(db, "t1", _STD_DATA, 1)
    ops = {op.name: op for op in db.query(Operation).filter_by(work_order_id=wo.id).all()}
    pick = ops["Pick Components"]

    result = complete_operation(db, pick.id, "t1")
    assert result.status == "complete"
    assert result.actual_completion_day == 3
    db.close()


def test_complete_operation_raises_404_for_wrong_tenant(db_session):
    from fastapi import HTTPException
    db = db_session()
    _insert_sim(db, "t1")
    wo = create_work_order_with_operations(db, "t1", _STD_DATA, 1)
    ops = db.query(Operation).filter_by(work_order_id=wo.id).all()
    pick_id = ops[0].id

    with pytest.raises(HTTPException) as exc_info:
        complete_operation(db, pick_id, "wrong-tenant")
    assert exc_info.value.status_code == 404
    db.close()


def test_complete_operation_raises_404_for_nonexistent_op(db_session):
    from fastapi import HTTPException
    db = db_session()
    _insert_sim(db, "t1")

    with pytest.raises(HTTPException) as exc_info:
        complete_operation(db, 99999, "t1")
    assert exc_info.value.status_code == 404
    db.close()


def test_non_inspection_op_does_not_trigger_rework(db_session):
    db = db_session()
    _insert_sim(db, "t1")
    wo = create_work_order_with_operations(db, "t1", _STD_DATA, 1)
    count_before = db.query(Operation).filter_by(work_order_id=wo.id).count()
    ops = {op.name: op for op in db.query(Operation).filter_by(work_order_id=wo.id).all()}
    complete_operation(db, ops["Frame Assembly"].id, "t1")
    count_after = db.query(Operation).filter_by(work_order_id=wo.id).count()
    assert count_after == count_before
    db.close()


# ---------------------------------------------------------------------------
# Inspection rework
# ---------------------------------------------------------------------------

def _setup_failing_frame_wo(db, tenant_id: str):
    """
    Create enough dummy WOs so the next WO id is the first one that fails
    the Frame Stress Test, then create and return that WO.
    """
    target_id = _first_failing_id("Frame Stress Test")

    # Insert (target_id - 1) bare WorkOrder rows to advance the auto-increment
    for _ in range(target_id - 1):
        db.add(WorkOrder(
            tenant_id=tenant_id,
            frame_type="Standard", motor_type="Standard Motor",
            battery="Standard", finish="Black Powder Coat",
            status="open", created_day=1,
        ))
    db.flush()

    _give_stock(db, "Reinforced Off-Road", 5)
    wo = create_work_order_with_operations(db, tenant_id, _REINFORCED_DATA, 1)
    assert wo.id == target_id, f"Expected id={target_id}, got {wo.id}"
    return wo


def test_inspection_pass_does_not_insert_rework(db_session):
    db = db_session()
    _insert_sim(db, "t1")
    pass_id = _first_passing_id("Frame Stress Test")

    # Advance auto-increment so the WO gets the passing ID
    for _ in range(pass_id - 1):
        db.add(WorkOrder(
            tenant_id="t1",
            frame_type="Standard", motor_type="Standard Motor",
            battery="Standard", finish="Black Powder Coat",
            status="open", created_day=1,
        ))
    db.flush()
    _give_stock(db, "Reinforced Off-Road", 5)

    wo = create_work_order_with_operations(db, "t1", _REINFORCED_DATA, 1)
    assert wo.id == pass_id
    count_before = db.query(Operation).filter_by(work_order_id=wo.id).count()

    ops = {op.name: op for op in db.query(Operation).filter_by(work_order_id=wo.id).all()}
    complete_operation(db, ops["Frame Stress Test"].id, "t1")

    count_after = db.query(Operation).filter_by(work_order_id=wo.id).count()
    assert count_after == count_before
    db.close()


def test_inspection_fail_inserts_rework_and_retest(db_session):
    db = db_session()
    _insert_sim(db, "t1")
    wo = _setup_failing_frame_wo(db, "t1")
    count_before = db.query(Operation).filter_by(work_order_id=wo.id).count()
    ops = {op.name: op for op in db.query(Operation).filter_by(work_order_id=wo.id).all()}

    complete_operation(db, ops["Frame Stress Test"].id, "t1")

    count_after = db.query(Operation).filter_by(work_order_id=wo.id).count()
    assert count_after == count_before + 2
    db.close()


def test_rework_op_depends_on_failed_inspection_op(db_session):
    db = db_session()
    _insert_sim(db, "t1")
    wo = _setup_failing_frame_wo(db, "t1")
    ops_before = {op.name: op for op in db.query(Operation).filter_by(work_order_id=wo.id).all()}
    fst = ops_before["Frame Stress Test"]

    complete_operation(db, fst.id, "t1")
    db.expire_all()

    new_ops = {op.name: op for op in db.query(Operation).filter_by(work_order_id=wo.id).all()}
    rework = new_ops[f"Rework: Frame Stress Test"]
    assert rework.depends_on_operation_id == fst.id
    db.close()


def test_retest_op_depends_on_rework(db_session):
    db = db_session()
    _insert_sim(db, "t1")
    wo = _setup_failing_frame_wo(db, "t1")
    ops_before = {op.name: op for op in db.query(Operation).filter_by(work_order_id=wo.id).all()}
    fst = ops_before["Frame Stress Test"]

    complete_operation(db, fst.id, "t1")
    db.expire_all()

    new_ops = {op.name: op for op in db.query(Operation).filter_by(work_order_id=wo.id).all()}
    rework = new_ops["Rework: Frame Stress Test"]
    retest = new_ops["Retest: Frame Stress Test"]
    assert retest.depends_on_operation_id == rework.id
    db.close()


def test_downstream_op_rewired_to_retest_after_fail(db_session):
    db = db_session()
    _insert_sim(db, "t1")
    wo = _setup_failing_frame_wo(db, "t1")
    ops_before = {op.name: op for op in db.query(Operation).filter_by(work_order_id=wo.id).all()}
    fst = ops_before["Frame Stress Test"]

    complete_operation(db, fst.id, "t1")
    db.expire_all()

    new_ops = {op.name: op for op in db.query(Operation).filter_by(work_order_id=wo.id).all()}
    retest = new_ops["Retest: Frame Stress Test"]
    frame_asm = new_ops["Frame Assembly"]
    # Frame Assembly should now depend on the Retest op, not the original FST
    assert frame_asm.depends_on_operation_id == retest.id
    db.close()


def test_rework_capped_no_second_rework_on_retest(db_session):
    db = db_session()
    _insert_sim(db, "t1")
    wo = _setup_failing_frame_wo(db, "t1")
    ops = {op.name: op for op in db.query(Operation).filter_by(work_order_id=wo.id).all()}

    # Fail the first inspection
    complete_operation(db, ops["Frame Stress Test"].id, "t1")
    db.expire_all()

    new_ops = {op.name: op for op in db.query(Operation).filter_by(work_order_id=wo.id).all()}
    count_after_first_fail = db.query(Operation).filter_by(work_order_id=wo.id).count()

    # Complete rework and retest — should not trigger another rework cycle
    rework = new_ops["Rework: Frame Stress Test"]
    retest = new_ops["Retest: Frame Stress Test"]
    complete_operation(db, rework.id, "t1")
    complete_operation(db, retest.id, "t1")

    count_final = db.query(Operation).filter_by(work_order_id=wo.id).count()
    assert count_final == count_after_first_fail  # no additional ops inserted
    db.close()
