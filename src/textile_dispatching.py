"""Deadline-first FIFO serial generation for the published textile semantics."""
from __future__ import annotations
from time import perf_counter
import pandas as pd
from .calendars import first_fit
from .scheduling_model import ScheduleResult
from .textile_data import TextileChoice, TextileInstance, TextileOperation
from .textile_validation import TEXTILE_COLUMNS, validate_textile_schedule


def textile_row(op: TextileOperation, choice: TextileChoice, start: int) -> dict:
    return {"operation_id": op.operation_id, "request_id": f"R{op.request_index+1:03d}", "unit_id": op.unit_id,
            "product": op.product, "task": op.task, "task_index": op.task_index + 1, "run_index": op.run_index,
            "machine_id": choice.machine_id, "mode_id": choice.mode_id, "start_slot": start,
            "end_slot": start + choice.duration, "duration_slots": choice.duration,
            "duration_minutes": 5 * choice.duration, "deadline_slot": op.deadline}


def dispatch_textile(instance: TextileInstance, *, load_bias: float = 0.0) -> ScheduleResult:
    """Schedule ready operations by deadline, then source request/unit/task/run.

    With the default zero bias this is the benchmark: choose the earliest finish.
    A positive bias additionally penalizes machine load and is used solely to
    construct a separately disclosed CP-SAT warm-start candidate. Both obey
    identical feasibility constraints. Greedy failure is not infeasibility.
    """
    if load_bias < 0:
        raise ValueError("load_bias must be nonnegative")
    clock = perf_counter()
    waiting = {op.operation_id: op for op in instance.operations}
    assigned = {}
    machine_busy = {m: [] for m in instance.machines}
    unit_busy: dict[str, list[tuple[int, int]]] = {}
    task_busy: dict[str, list[tuple[int, int]]] = {}
    while waiting:
        ready = [op for op in waiting.values() if all(pred in assigned for pred in op.predecessors)
                 and (op.symmetry_predecessor is None or op.symmetry_predecessor in assigned)]
        if not ready:
            return ScheduleResult("HEURISTIC_FAILED", objective="deadline_fifo", solve_seconds=perf_counter()-clock,
                                  message="No precedence-ready textile task; heuristic did not produce a schedule.")
        op = min(ready, key=lambda x: (x.deadline if x.deadline is not None else instance.horizon + 1,
                                       x.request_index, x.unit_index, x.task_index, x.run_index))
        earliest = max((assigned[x]["end_slot"] for x in op.predecessors), default=0)
        if op.symmetry_predecessor is not None:
            earliest = max(earliest, assigned[op.symmetry_predecessor]["start_slot"])
        colliding = []
        for a, b in instance.collision_pairs:
            if op.task == a: colliding.extend(task_busy.get(b, []))
            if op.task == b: colliding.extend(task_busy.get(a, []))
        candidates = []
        # The warm-start variant reserves capacity for unscheduled tasks that
        # have no alternative machine; the benchmark keeps zero bias.
        mandatory_load = {m: 0 for m in instance.machines}
        if load_bias:
            for pending in waiting.values():
                eligible_machines = {c.machine_id for c in pending.choices}
                if len(eligible_machines) == 1:
                    mandatory_load[next(iter(eligible_machines))] += min(c.duration for c in pending.choices)
        for choice in op.choices:
            blockers = machine_busy[choice.machine_id] + colliding
            if instance.unit_exclusive: blockers += unit_busy.get(op.unit_id, [])
            # The generic helper merges adjacent windows; a source time leap
            # must instead remain a hard task boundary even with no gap in slot IDs.
            start = next((s for window in instance.windows
                          if (s := first_fit([window], blockers, earliest, choice.duration)) is not None), None)
            if start is None or (op.deadline is not None and start + choice.duration > op.deadline):
                continue
            finish = start + choice.duration
            current_load = sum(b - a for a, b in machine_busy[choice.machine_id])
            score = finish + load_bias * (current_load + choice.duration + mandatory_load[choice.machine_id])
            candidates.append((score, finish, start, choice.machine_id, choice.mode_id, choice))
        if not candidates:
            return ScheduleResult("HEURISTIC_FAILED", objective="deadline_fifo", solve_seconds=perf_counter()-clock,
                                  message=f"Greedy dispatch could not place {op.operation_id}; this is not an infeasibility proof.")
        _, _, start, machine, _, choice = min(candidates, key=lambda x: x[:5])
        row = textile_row(op, choice, start)
        assigned[op.operation_id] = row
        machine_busy[machine].append((row["start_slot"], row["end_slot"]))
        unit_busy.setdefault(op.unit_id, []).append((row["start_slot"], row["end_slot"]))
        task_busy.setdefault(op.task, []).append((row["start_slot"], row["end_slot"]))
        del waiting[op.operation_id]
    schedule = pd.DataFrame(assigned.values(), columns=TEXTILE_COLUMNS).sort_values(["machine_id", "start_slot", "operation_id"]).reset_index(drop=True)
    errors = validate_textile_schedule(instance, schedule)
    if errors:
        raise RuntimeError("Invalid textile baseline: " + "; ".join(errors[:5]))
    return ScheduleResult("HEURISTIC", schedule=schedule, objective="deadline_fifo", solve_seconds=perf_counter()-clock,
                          message=("Deadline-first FIFO with earliest-finishing eligible mode; no optimality proof." if not load_bias else
                                   f"Load-balanced dispatch warm start (load bias {load_bias}); no optimality proof."),
                          metadata={"load_bias": load_bias})
