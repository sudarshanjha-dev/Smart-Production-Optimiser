"""Serial schedule generation with FIFO, EDD or SPT dispatch priorities."""
from __future__ import annotations
import pandas as pd
from .calendars import first_fit, machine_windows
from .data_loader import FactoryData, build_operations, schedule_row
from .scheduling_model import ScheduleResult, SCHEDULE_COLUMNS


def dispatch_schedule(factory: FactoryData, rule: str = "FIFO") -> ScheduleResult:
    rule = rule.upper()
    if rule not in {"FIFO", "EDD", "SPT"}:
        raise ValueError("Dispatch rule must be FIFO, EDD or SPT")
    operations = build_operations(factory)
    if not operations:
        return ScheduleResult("NO_ORDERS", objective=rule, message="No orders to schedule.")
    by_id = {op.operation_id: op for op in operations}
    unscheduled = set(by_id)
    completed: dict[str, dict] = {}
    windows = {m: machine_windows(factory, m) for m in factory.machines.machine_id}
    busy = {m: [] for m in windows}
    while unscheduled:
        ready = [by_id[x] for x in unscheduled if by_id[x].predecessor_id is None or by_id[x].predecessor_id in completed]
        if not ready:
            return ScheduleResult("HEURISTIC_FAILED", objective=rule, message="No precedence-ready operation.")
        def key(op):
            common = (op.order_index, op.sequence, op.operation_id)
            if rule == "FIFO": return (op.release,) + common
            if rule == "EDD": return (op.due, op.release) + common
            return (min(a.duration(op.quantity) for a in op.alternatives), op.release) + common
        op = min(ready, key=key)
        earliest = max(op.release, completed[op.predecessor_id]["finish"] if op.predecessor_id else 0)
        options = []
        for alt in op.alternatives:
            start = first_fit(windows[alt.machine_id], busy[alt.machine_id], earliest, alt.duration(op.quantity))
            if start is not None:
                options.append((start + alt.duration(op.quantity), start, alt.machine_id, alt))
        if not options:
            return ScheduleResult("HEURISTIC_FAILED", objective=rule,
                                  message=f"{rule} could not place {op.operation_id} within the horizon; this is not an infeasibility proof.")
        _, start, machine, alt = min(options, key=lambda x: x[:3])
        row = schedule_row(op, alt, start)
        completed[op.operation_id] = row
        busy[machine].append((row["start"], row["finish"]))
        unscheduled.remove(op.operation_id)
    schedule = pd.DataFrame(completed.values(), columns=SCHEDULE_COLUMNS).sort_values(["machine_id", "start", "operation_id"]).reset_index(drop=True)
    return ScheduleResult("HEURISTIC", schedule=schedule, objective=rule,
                          message="Greedy serial schedule; no optimality claim.")
