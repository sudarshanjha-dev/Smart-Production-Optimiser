"""Independent checks against input routings, clocks and resource occupancy."""
from __future__ import annotations
import math
import pandas as pd
from .calendars import machine_windows
from .data_loader import FactoryData, build_operations
from .scheduling_model import SCHEDULE_COLUMNS


def _int(value):
    try:
        n = float(value)
        if not math.isfinite(n) or not n.is_integer(): return None
        return int(n)
    except (ValueError, TypeError):
        return None


def validate_schedule(factory: FactoryData, schedule: pd.DataFrame, history: pd.DataFrame | None = None) -> list[str]:
    """Return all detected errors; an empty list means the required checks passed."""
    errors: list[str] = []
    missing = set(SCHEDULE_COLUMNS) - set(schedule.columns)
    if missing:
        return ["Schedule missing columns: " + ", ".join(sorted(missing))]
    ops = {x.operation_id: x for x in build_operations(factory)}
    ids = schedule.operation_id.astype(str).tolist()
    if len(ids) != len(set(ids)): errors.append("An operation is scheduled more than once")
    for x in sorted(set(ops) - set(ids)): errors.append(f"Missing required operation {x}")
    for x in sorted(set(ids) - set(ops)): errors.append(f"Unknown operation {x}")
    starts_ends = {}
    intervals: dict[str, list[tuple[int, int, str]]] = {m: [] for m in factory.machines.machine_id}
    windows = {m: machine_windows(factory, m) for m in intervals}
    for row in schedule.to_dict("records"):
        oid = str(row["operation_id"])
        if oid not in ops: continue
        op = ops[oid]
        start, finish = _int(row["start"]), _int(row["finish"])
        machine = str(row["machine_id"])
        if row["order_id"] != op.order_id or row["product_id"] != op.product_id or _int(row["operation_sequence"]) != op.sequence or _int(row["quantity"]) != op.quantity:
            errors.append(f"{oid}: order/product/sequence/quantity does not match the routing")
        pred = "" if pd.isna(row["predecessor_operation_id"]) else str(row["predecessor_operation_id"])
        if row["operation_name"] != op.name or pred != (op.predecessor_id or ""):
            errors.append(f"{oid}: operation name or predecessor does not match")
        if _int(row["release_minute"]) != op.release or _int(row["due_minute"]) != op.due or _int(row["priority"]) != op.priority:
            errors.append(f"{oid}: release, due or priority does not match")
        if row["segment_type"] != "scheduled": errors.append(f"{oid}: invalid segment type")
        alt = next((a for a in op.alternatives if a.machine_id == machine), None)
        if not alt: errors.append(f"{oid}: machine {machine} is not eligible")
        if start is None or finish is None or start < 0 or finish <= start or finish > factory.horizon:
            errors.append(f"{oid}: invalid start or finish")
            continue
        starts_ends[oid] = (start, finish)
        if start < op.release: errors.append(f"{oid}: starts before release")
        if alt:
            if finish - start != alt.duration(op.quantity) or _int(row["setup_minutes"]) != alt.setup_minutes or _int(row["processing_minutes"]) != alt.minutes_per_unit * op.quantity:
                errors.append(f"{oid}: setup or duration does not match routing and quantity")
            if not any(a <= start and finish <= b for a, b in windows[machine]):
                errors.append(f"{oid}: outside a continuous available machine window")
            intervals[machine].append((start, finish, oid))
    for oid, op in ops.items():
        if op.predecessor_id and oid in starts_ends and op.predecessor_id in starts_ends and starts_ends[oid][0] < starts_ends[op.predecessor_id][1]:
            errors.append(f"{oid}: precedence violated")
    if history is not None and not history.empty:
        needed = {"operation_id", "machine_id", "start", "finish", "segment_type"}
        if needed - set(history.columns):
            errors.append("Historical segment is missing required columns")
        else:
            for h in history.to_dict("records"):
                oid, m = str(h["operation_id"]), str(h["machine_id"])
                start, finish = _int(h["start"]), _int(h["finish"])
                if oid not in ops or not any(a.machine_id == m for a in ops[oid].alternatives):
                    errors.append(f"Historical segment {oid}: invalid operation or machine")
                elif h["segment_type"] != "aborted" or start is None or finish is None or not (0 <= start < finish <= factory.horizon):
                    errors.append(f"Historical segment {oid}: invalid interval or segment type")
                else:
                    if not any(a <= start and finish <= b for a, b in windows[m]):
                        errors.append(f"Historical segment {oid}: outside availability")
                    if oid in starts_ends and starts_ends[oid][0] < finish:
                        errors.append(f"{oid}: restart precedes aborted work")
                    intervals[m].append((start, finish, oid + " (aborted)"))
    for m, items in intervals.items():
        items.sort()
        for prev, curr in zip(items, items[1:]):
            if prev[1] > curr[0]: errors.append(f"{m}: overlap between {prev[2]} and {curr[2]}")
    return errors
