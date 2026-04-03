"""
Scheduling algorithm for manufacturing operations.

Pure logic — no database access. Takes a list of Operation ORM objects
(already in-session, can be mutated), assigns scheduled_start_day and
scheduled_end_day respecting:
  - dependency ordering (an op cannot start before its dependency ends)
  - work center daily capacity limits
"""
from collections import defaultdict, deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Operation

# Operations per work center per day. Missing keys = unlimited.
CAPACITIES: dict[str, int] = {
    "Assembly": 2,
    "Inspection": 2,
    "Finishing": 1,
}
_UNLIMITED = 999


def reschedule_all(ops: list["Operation"], current_day: int) -> list["Operation"]:
    """
    Schedule (or re-schedule) all provided operations starting from current_day.

    Operations already marked 'complete' are skipped but their end days are
    used when computing how early dependent ops can start.

    Algorithm:
      1. Topological sort via Kahn's BFS on depends_on_operation_id.
      2. Walk ops in dependency order, assigning the earliest available day
         that satisfies both the dependency constraint and work center capacity.
    """
    if not ops:
        return ops

    op_map: dict[int, "Operation"] = {op.id: op for op in ops}

    # --- Topological sort (Kahn's BFS) ---
    # Build in-degree and adjacency list using depends_on_operation_id
    in_degree: dict[int, int] = {op.id: 0 for op in ops}
    children: dict[int, list[int]] = defaultdict(list)  # parent id → child ids

    for op in ops:
        dep_id = op.depends_on_operation_id
        if dep_id and dep_id in op_map:
            in_degree[op.id] += 1
            children[dep_id].append(op.id)
        # If the dependency is outside this batch (e.g., already-complete op not in list),
        # we still need its end day. We'll handle that below when looking up dep end days.

    queue: deque[int] = deque(
        op_id for op_id, deg in in_degree.items() if deg == 0
    )
    ordered: list["Operation"] = []

    while queue:
        op_id = queue.popleft()
        op = op_map[op_id]
        ordered.append(op)
        for child_id in children[op_id]:
            in_degree[child_id] -= 1
            if in_degree[child_id] == 0:
                queue.append(child_id)

    # Any ops not reachable (e.g., cycle or orphan) get appended at end
    scheduled_ids = {op.id for op in ordered}
    for op in ops:
        if op.id not in scheduled_ids:
            ordered.append(op)

    # --- Capacity tracking: work_center → day → count ---
    capacity_used: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))

    # --- Assign days ---
    # We need a global lookup for end days, including ops outside this batch.
    # Build it from all ops we have; complete ops outside batch won't be in op_map.
    end_day_by_id: dict[int, int] = {}
    for op in ops:
        if op.status == "complete" and op.scheduled_end_day is not None:
            end_day_by_id[op.id] = op.scheduled_end_day

    for op in ordered:
        if op.status == "complete":
            # Preserve existing schedule; record end day for dependents.
            if op.scheduled_end_day is not None:
                end_day_by_id[op.id] = op.scheduled_end_day
            continue

        # Earliest start = current_day, or after dependency ends (whichever is later)
        earliest = current_day
        dep_id = op.depends_on_operation_id
        if dep_id:
            dep_end = end_day_by_id.get(dep_id)
            if dep_end is not None:
                earliest = max(earliest, dep_end)

        # Find first day at or after earliest where work center has capacity
        cap = CAPACITIES.get(op.work_center, _UNLIMITED)
        day = earliest
        while capacity_used[op.work_center][day] >= cap:
            day += 1

        op.scheduled_start_day = day
        op.scheduled_end_day = day + op.duration_days
        capacity_used[op.work_center][day] += 1
        end_day_by_id[op.id] = op.scheduled_end_day

    return ops
