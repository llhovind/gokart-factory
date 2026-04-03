"""
Business logic layer: work order creation, operation completion (with inspection
rework), and simulation time advancement.
"""
import hashlib
from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import Operation, SimulationState, WorkOrder
from .schemas import WorkOrderCreate
from . import scheduler


# ---------------------------------------------------------------------------
# Operation template for a work order
# ---------------------------------------------------------------------------

def _operation_templates(wo: WorkOrder) -> list[dict]:
    """
    Return the ordered list of manufacturing operations for a given work order.
    The 'depends_on' field is a name reference resolved after DB insertion.
    """
    motor_days = 2 if wo.motor_type == "High Torque Motor" else 1
    return [
        {"name": "Pick Components",    "work_center": "Inventory",   "duration_days": 1,          "depends_on": None},
        {"name": "Receive Motor",       "work_center": "Receiving",   "duration_days": motor_days, "depends_on": "Pick Components"},
        {"name": "Frame Stress Test",   "work_center": "Inspection",  "duration_days": 1,          "depends_on": "Receive Motor"},
        {"name": "Motor Torque Test",   "work_center": "Inspection",  "duration_days": 1,          "depends_on": "Frame Stress Test"},
        {"name": "Frame Assembly",      "work_center": "Assembly",    "duration_days": 2,          "depends_on": "Motor Torque Test"},
        {"name": "Motor Installation",  "work_center": "Assembly",    "duration_days": 1,          "depends_on": "Frame Assembly"},
        {"name": "Final Assembly",      "work_center": "Assembly",    "duration_days": 2,          "depends_on": "Motor Installation"},
        {"name": "Powder Coat",         "work_center": "Finishing",   "duration_days": 1,          "depends_on": "Final Assembly"},
        {"name": "Final QC",            "work_center": "Inspection",  "duration_days": 1,          "depends_on": "Powder Coat"},
        {"name": "Ship Order",          "work_center": "Shipping",    "duration_days": 1,          "depends_on": "Final QC"},
    ]


# ---------------------------------------------------------------------------
# Work order creation
# ---------------------------------------------------------------------------

def create_work_order_with_operations(
    db: Session,
    tenant_id: str,
    data: WorkOrderCreate,
    current_day: int,
) -> WorkOrder:
    """
    1. Insert WorkOrder
    2. Generate Operation rows (no deps yet)
    3. Flush to get DB-assigned IDs
    4. Wire depends_on_operation_id by name (second pass)
    5. Schedule all ops
    6. Commit and return
    """
    wo = WorkOrder(
        tenant_id=tenant_id,
        frame_type=data.frame_type,
        motor_type=data.motor_type,
        battery=data.battery,
        finish=data.finish,
        status="open",
        created_day=current_day,
    )
    db.add(wo)
    db.flush()  # Get wo.id

    templates = _operation_templates(wo)
    ops: list[Operation] = []
    for tmpl in templates:
        op = Operation(
            tenant_id=tenant_id,
            work_order_id=wo.id,
            name=tmpl["name"],
            work_center=tmpl["work_center"],
            duration_days=tmpl["duration_days"],
            status="planned",
        )
        db.add(op)
        ops.append(op)

    db.flush()  # Get op IDs so we can wire dependencies

    # Map name → op for dependency resolution
    name_to_op = {op.name: op for op in ops}
    for tmpl, op in zip(templates, ops):
        dep_name = tmpl["depends_on"]
        if dep_name and dep_name in name_to_op:
            op.depends_on_operation_id = name_to_op[dep_name].id

    scheduler.reschedule_all(ops, current_day)
    db.commit()
    db.refresh(wo)
    return wo


# ---------------------------------------------------------------------------
# Inspection result (deterministic across restarts)
# ---------------------------------------------------------------------------

def _inspection_result(work_order_id: int, op_name: str) -> int:
    """
    Deterministic 0-99 result for an inspection operation.
    Uses MD5 (not Python's hash()) so results are stable across server restarts.
    """
    key = f"{work_order_id}{op_name}".encode()
    return int(hashlib.md5(key).hexdigest(), 16) % 100


# ---------------------------------------------------------------------------
# Operation completion
# ---------------------------------------------------------------------------

_INSPECTION_OPS = {"Frame Stress Test", "Motor Torque Test"}
_THRESHOLDS = {"Frame Stress Test": 15, "Motor Torque Test": 10}


def complete_operation(db: Session, op_id: int, tenant_id: str) -> Operation:
    """
    Mark an operation complete. For inspection operations, run deterministic
    failure check. On failure (and rework_count < 1), insert a Rework op +
    Retest op, rewire the downstream dependency, and reschedule.
    """
    op = (
        db.query(Operation)
        .filter(Operation.id == op_id, Operation.tenant_id == tenant_id)
        .first()
    )
    if not op:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Operation not found")

    op.status = "complete"

    rework_added = False

    if op.name in _INSPECTION_OPS and op.rework_count < 1:
        result = _inspection_result(op.work_order_id, op.name)
        threshold = _THRESHOLDS[op.name]

        if result < threshold:
            # Inspection failed — insert rework + retest
            rework_op = Operation(
                tenant_id=tenant_id,
                work_order_id=op.work_order_id,
                name=f"Rework: {op.name}",
                work_center=op.work_center,
                duration_days=1,
                status="planned",
                depends_on_operation_id=op.id,
                rework_count=op.rework_count + 1,
            )
            db.add(rework_op)
            db.flush()

            retest_op = Operation(
                tenant_id=tenant_id,
                work_order_id=op.work_order_id,
                name=f"Retest: {op.name}",
                work_center=op.work_center,
                duration_days=1,
                status="planned",
                depends_on_operation_id=rework_op.id,
                rework_count=op.rework_count + 1,
            )
            db.add(retest_op)
            db.flush()

            # Rewire the op that originally depended on the failed inspection
            # so it now waits for the retest instead.
            next_op = (
                db.query(Operation)
                .filter(
                    Operation.depends_on_operation_id == op.id,
                    Operation.tenant_id == tenant_id,
                    Operation.id != rework_op.id,
                )
                .first()
            )
            if next_op:
                next_op.depends_on_operation_id = retest_op.id

            rework_added = True

    if rework_added:
        # Re-schedule all non-complete ops so the rework fits into capacity
        sim = db.query(SimulationState).filter_by(tenant_id=tenant_id).first()
        all_live_ops = (
            db.query(Operation)
            .filter(Operation.tenant_id == tenant_id, Operation.status != "complete")
            .all()
        )
        scheduler.reschedule_all(all_live_ops, sim.current_day if sim else 1)

    db.commit()
    db.refresh(op)
    return op


# ---------------------------------------------------------------------------
# Simulation advancement
# ---------------------------------------------------------------------------

def _update_statuses(db: Session, tenant_id: str, current_day: int) -> None:
    """
    Transition operation statuses based on the new current_day:
      planned → ready          when start_day <= current_day and dep is complete
      ready   → awaiting_completion  when end_day <= current_day and dep is complete
    """
    ops = (
        db.query(Operation)
        .filter(Operation.tenant_id == tenant_id, Operation.status != "complete")
        .all()
    )

    # Build a quick lookup for dep status
    all_ops_by_id = {op.id: op for op in ops}
    # Also include complete ops (deps may already be complete and not in live list)
    complete_op_ids: set[int] = set(
        row[0]
        for row in db.query(Operation.id)
        .filter(Operation.tenant_id == tenant_id, Operation.status == "complete")
        .all()
    )

    def dep_done(op: Operation) -> bool:
        dep_id = op.depends_on_operation_id
        if dep_id is None:
            return True
        if dep_id in complete_op_ids:
            return True
        dep = all_ops_by_id.get(dep_id)
        return dep is not None and dep.status == "complete"

    for op in ops:
        if not dep_done(op):
            continue
        if op.scheduled_end_day is not None and op.scheduled_end_day <= current_day:
            op.status = "awaiting_completion"
        elif op.scheduled_start_day is not None and op.scheduled_start_day <= current_day:
            if op.status == "planned":
                op.status = "ready"


def advance_simulation(
    db: Session,
    tenant_id: str,
    days: int | None,
    mode: str | None,
) -> SimulationState:
    """
    Advance the factory clock then update all operation statuses.
    mode='next_event' jumps to the earliest future scheduled_start_day.
    """
    sim = db.query(SimulationState).filter_by(tenant_id=tenant_id).first()
    if not sim:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Simulation state not found")

    if mode == "next_event":
        # Jump to the earliest upcoming operation start day
        next_day = (
            db.query(func.min(Operation.scheduled_start_day))
            .filter(
                Operation.tenant_id == tenant_id,
                Operation.scheduled_start_day > sim.current_day,
                Operation.status.notin_(["complete"]),
            )
            .scalar()
        )
        if next_day is not None:
            sim.current_day = next_day
    else:
        sim.current_day += days or 1

    _update_statuses(db, tenant_id, sim.current_day)
    db.commit()
    db.refresh(sim)
    return sim
