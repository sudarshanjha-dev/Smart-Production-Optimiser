"""Independent validation of real-textile task schedules."""
from __future__ import annotations
import math
import pandas as pd
from .textile_data import TextileInstance

TEXTILE_COLUMNS = ["operation_id", "request_id", "unit_id", "product", "task", "task_index", "run_index",
                   "machine_id", "mode_id", "start_slot", "end_slot", "duration_slots", "duration_minutes", "deadline_slot"]


def _integer(value):
    if isinstance(value, bool): return None
    try:
        n = float(value)
        return int(n) if math.isfinite(n) and n.is_integer() else None
    except (TypeError, ValueError, OverflowError):
        return None


def validate_textile_schedule(instance: TextileInstance, schedule: pd.DataFrame, *, makespan_limit: int | None = None) -> list[str]:
    if not isinstance(schedule, pd.DataFrame): return ["Schedule must be a pandas DataFrame"]
    missing = set(TEXTILE_COLUMNS) - set(schedule.columns)
    if missing: return ["Schedule missing fields: " + ", ".join(sorted(missing))]
    errors: list[str] = []
    expected = {op.operation_id: op for op in instance.operations}
    ids = schedule.operation_id.astype(str).tolist()
    if len(ids) != len(set(ids)): errors.append("A task run appears more than once")
    for oid in sorted(set(expected) - set(ids)): errors.append(f"Missing task run {oid}")
    for oid in sorted(set(ids) - set(expected)): errors.append(f"Unknown task run {oid}")
    occupied: dict[str, list[tuple[int, int, str]]] = {m: [] for m in instance.machines}
    units: dict[str, list[tuple[int, int, str]]] = {}
    times: dict[str, tuple[int, int]] = {}
    by_task: dict[str, list[tuple[int, int, str]]] = {}
    for row in schedule.to_dict("records"):
        oid = str(row["operation_id"])
        if oid not in expected: continue
        op = expected[oid]
        if (row["request_id"] != f"R{op.request_index+1:03d}" or row["unit_id"] != op.unit_id or
            row["product"] != op.product or row["task"] != op.task or
            _integer(row["task_index"]) != op.task_index + 1 or _integer(row["run_index"]) != op.run_index):
            errors.append(f"{oid}: product, task, request, unit or run metadata differs from the input")
        deadline_missing = pd.isna(row["deadline_slot"])
        deadline = None if deadline_missing else _integer(row["deadline_slot"])
        if (not deadline_missing and deadline is None) or deadline != op.deadline:
            errors.append(f"{oid}: deadline differs from the input")
        machine, mode = str(row["machine_id"]), str(row["mode_id"])
        choice = next((c for c in op.choices if c.machine_id == machine and c.mode_id == mode), None)
        if choice is None: errors.append(f"{oid}: incompatible machine/mode {machine} / {mode}")
        start, end = _integer(row["start_slot"]), _integer(row["end_slot"])
        if start is None or end is None or not (0 <= start < end <= instance.horizon):
            errors.append(f"{oid}: invalid slot interval"); continue
        times[oid] = (start, end)
        if choice is not None:
            if (end - start != choice.duration or _integer(row["duration_slots"]) != choice.duration or
                _integer(row["duration_minutes"]) != choice.duration * 5):
                errors.append(f"{oid}: duration does not match selected task mode")
        if makespan_limit is not None and end > makespan_limit:
            errors.append(f"{oid}: makespan cap violated")
        if any(start < leap < end for leap in instance.time_leaps):
            errors.append(f"{oid}: crosses a source time leap")
        if op.deadline is not None and end > op.deadline: errors.append(f"{oid}: source deadline violated")
        if machine in occupied: occupied[machine].append((start, end, oid))
        units.setdefault(op.unit_id, []).append((start, end, oid))
        by_task.setdefault(op.task, []).append((start, end, oid))
    for op in instance.operations:
        if op.operation_id not in times: continue
        for pred in op.predecessors:
            if pred in times and times[pred][1] > times[op.operation_id][0]:
                errors.append(f"{op.operation_id}: task-order precedence violated ({pred})")
        if op.symmetry_predecessor in times and times[op.symmetry_predecessor][0] > times[op.operation_id][0]:
            errors.append(f"{op.operation_id}: interchangeable run start-label order violated")
    resource_groups = [("Machine", occupied)]
    if instance.unit_exclusive: resource_groups.append(("Product unit", units))
    for name, groups in resource_groups:
        for group, spans in groups.items():
            spans.sort()
            for prev, curr in zip(spans, spans[1:]):
                if prev[1] > curr[0]: errors.append(f"{name} {group}: overlap between {prev[2]} and {curr[2]}")
    for task1, task2 in instance.collision_pairs:
        for a_start, a_end, a_id in by_task.get(task1, []):
            for b_start, b_end, b_id in by_task.get(task2, []):
                if a_start < b_end and b_start < a_end:
                    errors.append(f"Collision constraint: {a_id} overlaps {b_id}")
    return errors
