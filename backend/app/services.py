"""
Business logic layer: work order creation, operation completion (with inspection
rework), and simulation time advancement.
"""
import hashlib
from sqlalchemy import func
from sqlalchemy.orm import Session

from fastapi import HTTPException
from .models import InventoryItem, Operation, SimulationState, WorkOrder
from .schemas import WorkOrderCreate
from . import scheduler


# ---------------------------------------------------------------------------
# Inventory seed data
# ---------------------------------------------------------------------------

_INVENTORY_SEED = [
    # (category, name, requires_pre_assembly_test, receive_duration_days, qty_on_hand)
    ("frame",   "Standard",            False, None, 6),
    ("frame",   "Reinforced Off-Road", True,  None, 0),
    ("motor",   "Standard Motor",      False, 1,    6),
    ("motor",   "High Torque Motor",   True,  2,    0),
    ("battery", "Standard",            False, None, 6),
    ("battery", "Competition",         True,  None, 0),
    ("finish",  "Black Powder Coat",   False, None, None),  # infinite
    ("finish",  "Red Powder Coat",     False, None, None),  # infinite
]


def seed_inventory(db: Session) -> None:
    """Idempotent — inserts seed items that don't already exist.
    Also updates requires_pre_assembly_test and initializes qty_on_hand=NULL
    rows (e.g. when the column is newly added to an existing DB)."""
    for category, name, test, days, qty in _INVENTORY_SEED:
        item = db.query(InventoryItem).filter_by(name=name, category=category).first()
        if not item:
            db.add(InventoryItem(
                name=name,
                category=category,
                requires_pre_assembly_test=test,
                receive_duration_days=days,
                qty_on_hand=qty,
            ))
        else:
            item.requires_pre_assembly_test = test
            if item.qty_on_hand is None and qty is not None:
                item.qty_on_hand = qty
    db.commit()


# ---------------------------------------------------------------------------
# Operation template for a work order
# ---------------------------------------------------------------------------

def _operation_templates(
    wo: WorkOrder,
    frame_item: InventoryItem,
    motor_item: InventoryItem,
    battery_item: InventoryItem,
) -> list[dict]:
    """
    Return the ordered list of manufacturing operations for a given work order.
    Pre-assembly tests are included only when the part's requires_pre_assembly_test
    flag is True. A Backorder Parts op is inserted when any stockable part has
    qty_on_hand == 0. The 'depends_on' field is a name reference resolved after DB insertion.
    """
    include_frame_test = frame_item.requires_pre_assembly_test
    include_motor_test = motor_item.requires_pre_assembly_test

    backordered_items = [
        item for item in [frame_item, motor_item, battery_item]
        if item.qty_on_hand is not None and item.qty_on_hand == 0
    ]
    needs_backorder = bool(backordered_items)

    if needs_backorder:
        # Duration = longest supplier lead time among backordered parts (min 1 day)
        receive_days = max(item.receive_duration_days or 1 for item in backordered_items)
        ops = [
            {"name": "Backorder Parts",  "work_center": "Purchasing", "duration_days": 1,            "depends_on": None},
            {"name": "Receive Parts",    "work_center": "Receiving",  "duration_days": receive_days, "depends_on": "Backorder Parts"},
            {"name": "Pick Components",  "work_center": "Inventory",  "duration_days": 1,            "depends_on": "Receive Parts"},
        ]
        after_pick = "Pick Components"
    else:
        ops = [
            {"name": "Pick Components",  "work_center": "Inventory",  "duration_days": 1, "depends_on": None},
        ]
        after_pick = "Pick Components"

    if include_frame_test:
        ops.append({"name": "Frame Stress Test", "work_center": "IQC", "duration_days": 1, "depends_on": after_pick})
    if include_motor_test:
        prev = "Frame Stress Test" if include_frame_test else after_pick
        ops.append({"name": "Motor Torque Test", "work_center": "IQC", "duration_days": 1, "depends_on": prev})

    last_test = (
        "Motor Torque Test" if include_motor_test
        else "Frame Stress Test" if include_frame_test
        else after_pick
    )

    ops += [
        {"name": "Frame Assembly",     "work_center": "Assembly",   "duration_days": 2, "depends_on": last_test},
        {"name": "Motor Installation", "work_center": "Assembly",   "duration_days": 1, "depends_on": "Frame Assembly"},
        {"name": "Final Assembly",     "work_center": "Assembly",   "duration_days": 2, "depends_on": "Motor Installation"},
        {"name": "Powder Coat",        "work_center": "Finishing",  "duration_days": 1, "depends_on": "Final Assembly"},
        {"name": "Final QC",           "work_center": "Inspection", "duration_days": 1, "depends_on": "Powder Coat"},
        {"name": "Ship Order",         "work_center": "Shipping",   "duration_days": 1, "depends_on": "Final QC"},
    ]
    return ops


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
    # Validate and retrieve inventory items (raises 422 if unknown or deprecated)
    checks = [
        ("frame",   data.frame_type),
        ("motor",   data.motor_type),
        ("battery", data.battery),
        ("finish",  data.finish),
    ]
    items: dict[str, InventoryItem] = {}
    for category, name in checks:
        item = db.query(InventoryItem).filter_by(
            category=category, name=name, deprecated=False
        ).first()
        if not item:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown or unavailable {category}: '{name}'"
            )
        items[category] = item

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

    templates = _operation_templates(wo, items["frame"], items["motor"], items["battery"])
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

    # Decrement qty_on_hand for stockable parts consumed by this work order
    for category in ("frame", "motor", "battery"):
        item = items[category]
        if item.qty_on_hand is not None and item.qty_on_hand > 0:
            item.qty_on_hand -= 1
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
        raise HTTPException(status_code=404, detail="Operation not found")

    sim = db.query(SimulationState).filter_by(tenant_id=tenant_id).first()
    current_day = sim.current_day if sim else 1

    op.status = "complete"
    op.actual_completion_day = current_day

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

    # Always reschedule — actual completion day may differ from scheduled,
    # so downstream operations need to be pushed forward or pulled in accordingly.
    all_ops = db.query(Operation).filter(Operation.tenant_id == tenant_id).all()
    scheduler.reschedule_all(all_ops, current_day)

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

    # Propagate any overdue awaiting_completion ops into downstream scheduled dates
    all_ops = db.query(Operation).filter(Operation.tenant_id == tenant_id).all()
    scheduler.reschedule_all(all_ops, sim.current_day)

    db.commit()
    db.refresh(sim)
    return sim
