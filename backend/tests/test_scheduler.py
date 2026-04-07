"""
Pure unit tests for app/scheduler.py.

No database or HTTP involved — uses a FakeOp dataclass that duck-types
the Operation ORM model fields that reschedule_all reads/writes.
"""
from dataclasses import dataclass, field
from app.scheduler import reschedule_all


@dataclass
class FakeOp:
    id: int
    name: str
    work_center: str
    duration_days: int
    depends_on_operation_id: int | None = None
    status: str = "planned"
    scheduled_start_day: int | None = None
    scheduled_end_day: int | None = None
    actual_completion_day: int | None = None
    rework_count: int = 0


# ---------------------------------------------------------------------------
# Basic correctness
# ---------------------------------------------------------------------------

def test_empty_list_returns_empty():
    assert reschedule_all([], current_day=1) == []


def test_single_op_no_dependency_starts_at_current_day():
    op = FakeOp(id=1, name="Pick", work_center="Inventory", duration_days=1)
    reschedule_all([op], current_day=5)
    assert op.scheduled_start_day == 5
    assert op.scheduled_end_day == 6


def test_current_day_is_always_the_floor():
    op = FakeOp(id=1, name="Ship", work_center="Shipping", duration_days=1)
    reschedule_all([op], current_day=10)
    assert op.scheduled_start_day == 10


# ---------------------------------------------------------------------------
# Standard 7-op linear chain
# ---------------------------------------------------------------------------

def _make_standard_chain() -> list[FakeOp]:
    """Mirrors the standard WO op sequence used by _operation_templates."""
    ops = [
        FakeOp(1, "Pick Components",  "Inventory",  1),
        FakeOp(2, "Frame Assembly",   "Assembly",   2, depends_on_operation_id=1),
        FakeOp(3, "Motor Installation","Assembly",  1, depends_on_operation_id=2),
        FakeOp(4, "Final Assembly",   "Assembly",   2, depends_on_operation_id=3),
        FakeOp(5, "Powder Coat",      "Finishing",  1, depends_on_operation_id=4),
        FakeOp(6, "Final QC",         "Inspection", 1, depends_on_operation_id=5),
        FakeOp(7, "Ship Order",       "Shipping",   1, depends_on_operation_id=6),
    ]
    return ops


def test_linear_chain_correct_start_and_end_days():
    ops = _make_standard_chain()
    reschedule_all(ops, current_day=1)
    by_id = {op.id: op for op in ops}

    assert (by_id[1].scheduled_start_day, by_id[1].scheduled_end_day) == (1, 2)
    assert (by_id[2].scheduled_start_day, by_id[2].scheduled_end_day) == (2, 4)
    assert (by_id[3].scheduled_start_day, by_id[3].scheduled_end_day) == (4, 5)
    assert (by_id[4].scheduled_start_day, by_id[4].scheduled_end_day) == (5, 7)
    assert (by_id[5].scheduled_start_day, by_id[5].scheduled_end_day) == (7, 8)
    assert (by_id[6].scheduled_start_day, by_id[6].scheduled_end_day) == (8, 9)
    assert (by_id[7].scheduled_start_day, by_id[7].scheduled_end_day) == (9, 10)


# ---------------------------------------------------------------------------
# Work center capacity
# ---------------------------------------------------------------------------

def test_assembly_capacity_two_per_day():
    ops = [
        FakeOp(1, "A1", "Assembly", 1),
        FakeOp(2, "A2", "Assembly", 1),
        FakeOp(3, "A3", "Assembly", 1),  # should be bumped to day 2
    ]
    reschedule_all(ops, current_day=1)
    starts = sorted(op.scheduled_start_day for op in ops)
    assert starts == [1, 1, 2]


def test_finishing_capacity_one_per_day():
    ops = [
        FakeOp(1, "F1", "Finishing", 1),
        FakeOp(2, "F2", "Finishing", 1),
    ]
    reschedule_all(ops, current_day=1)
    starts = sorted(op.scheduled_start_day for op in ops)
    assert starts == [1, 2]


def test_receiving_capacity_three_per_day():
    ops = [FakeOp(i, f"R{i}", "Receiving", 1) for i in range(1, 5)]
    reschedule_all(ops, current_day=1)
    starts = sorted(op.scheduled_start_day for op in ops)
    assert starts == [1, 1, 1, 2]


def test_iqc_capacity_two_per_day():
    ops = [FakeOp(i, f"IQC{i}", "IQC", 1) for i in range(1, 4)]
    reschedule_all(ops, current_day=1)
    starts = sorted(op.scheduled_start_day for op in ops)
    assert starts == [1, 1, 2]


def test_unlimited_capacity_work_center():
    ops = [FakeOp(i, f"S{i}", "Shipping", 1) for i in range(1, 6)]
    reschedule_all(ops, current_day=1)
    assert all(op.scheduled_start_day == 1 for op in ops)


# ---------------------------------------------------------------------------
# Handling complete / in-progress operations
# ---------------------------------------------------------------------------

def test_complete_op_actual_completion_day_used_over_scheduled():
    """actual_completion_day should be used (not scheduled_end_day) for downstream timing."""
    op1 = FakeOp(1, "Done", "Inventory", 1, status="complete",
                 scheduled_end_day=5, actual_completion_day=3)
    op2 = FakeOp(2, "Next", "Assembly", 1, depends_on_operation_id=1)
    reschedule_all([op1, op2], current_day=1)
    # downstream should wait for actual completion (3), not scheduled_end (5)
    assert op2.scheduled_start_day == 3
    assert op2.scheduled_end_day == 4


def test_complete_op_preserves_its_own_schedule():
    op1 = FakeOp(1, "Done", "Inventory", 1, status="complete",
                 scheduled_start_day=2, scheduled_end_day=3, actual_completion_day=3)
    op2 = FakeOp(2, "Next", "Shipping", 1, depends_on_operation_id=1)
    reschedule_all([op1, op2], current_day=1)
    # complete op's start/end should not be changed
    assert op1.scheduled_start_day == 2
    assert op1.scheduled_end_day == 3


def test_ready_op_is_not_rescheduled_but_end_day_used_for_downstream():
    op1 = FakeOp(1, "InProg", "Assembly", 2,
                 status="ready", scheduled_start_day=2, scheduled_end_day=4)
    op2 = FakeOp(2, "Next", "Shipping", 1, depends_on_operation_id=1)
    reschedule_all([op1, op2], current_day=3)
    # op1 must not be rescheduled
    assert op1.scheduled_start_day == 2
    assert op1.scheduled_end_day == 4
    # op2 must wait until op1's end
    assert op2.scheduled_start_day == 4


def test_awaiting_completion_overdue_pushes_downstream():
    """If an awaiting_completion op is overdue, downstream is scheduled from current_day."""
    op1 = FakeOp(1, "Overdue", "Assembly", 1,
                 status="awaiting_completion", scheduled_end_day=3)
    op2 = FakeOp(2, "Next", "Shipping", 1, depends_on_operation_id=1)
    reschedule_all([op1, op2], current_day=5)
    # effective end = max(scheduled_end=3, current_day=5) = 5
    assert op2.scheduled_start_day == 5


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_dependency_outside_batch_falls_back_to_current_day():
    """Dep ID not in the batch → op is treated as if it has no constraint."""
    op = FakeOp(1, "Orphan", "Inventory", 1, depends_on_operation_id=999)
    reschedule_all([op], current_day=3)
    assert op.scheduled_start_day == 3


def test_orphan_op_without_dep_in_batch_is_still_scheduled():
    op_a = FakeOp(1, "A", "Inventory", 1)
    op_b = FakeOp(2, "B", "Shipping",  1, depends_on_operation_id=1)
    op_c = FakeOp(3, "C", "Inventory", 1)  # no dep, independent
    reschedule_all([op_a, op_b, op_c], current_day=1)
    # All three should get valid dates
    for op in [op_a, op_b, op_c]:
        assert op.scheduled_start_day is not None
        assert op.scheduled_end_day is not None
