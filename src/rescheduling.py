"""Re-optimize after a breakdown or an urgent arrival; preserve actual history."""
from __future__ import annotations
import pandas as pd
from .data_loader import FactoryData
from .schedule_validator import validate_schedule
from .scheduling_model import ScheduleResult, SCHEDULE_COLUMNS, solve_schedule


def _check_original(factory: FactoryData, original: pd.DataFrame, now: int) -> None:
    if not isinstance(now, int) or not 0 <= now < factory.horizon:
        raise ValueError("Decision time must be an integer minute inside the horizon")
    problems = validate_schedule(factory, original)
    if problems:
        raise ValueError("The original schedule must be valid: " + "; ".join(problems[:3]))


def _freeze(original: pd.DataFrame, now: int, interrupted: set[str] | None = None):
    interrupted = interrupted or set()
    fixed, earliest = {}, {}
    for row in original.to_dict("records"):
        oid = row["operation_id"]
        # At exactly the start instant, the operation has not started yet.
        if row["finish"] <= now or (row["start"] < now < row["finish"] and oid not in interrupted):
            fixed[oid] = row
        else:
            earliest[oid] = now
    return fixed, earliest


def _check_result(factory: FactoryData, result: ScheduleResult, fixed: dict[str, dict]) -> None:
    if not result.has_schedule:
        return
    errors = validate_schedule(factory, result.schedule, result.history)
    new = result.schedule.set_index("operation_id")
    for oid, old in fixed.items():
        if oid not in new.index or any(new.loc[oid, c] != old[c] for c in ("machine_id", "start", "finish")):
            errors.append(f"Frozen operation {oid} was changed")
    if errors:
        raise RuntimeError("Rescheduler generated an invalid schedule: " + "; ".join(errors[:5]))


def reschedule_breakdown(factory: FactoryData, original: pd.DataFrame, machine_id: str,
                         start: int, end: int, time_limit: float = 10, workers: int = 4) -> tuple[FactoryData, ScheduleResult]:
    """Abort the running broken-machine operation; restart it in full on that
    same machine after repair. The prior partial interval is recorded as wasted
    work. Completed operations and running work on other machines are frozen.
    """
    _check_original(factory, original, start)
    if machine_id not in set(factory.machines.machine_id):
        raise ValueError("Unknown machine")
    if not isinstance(end, int) or not start < end <= factory.horizon:
        raise ValueError("Breakdown end must be after the start and within the horizon")
    overlaps = original[(original.machine_id == machine_id) & (original.start < end) & (original.finish > start)]
    running = overlaps[(overlaps.start < start) & (overlaps.finish > start)]
    interrupted = set(running.operation_id)
    history = running.copy()
    if not history.empty:
        history.loc[:, "finish"] = start
        history.loc[:, "segment_type"] = "aborted"
    else:
        history = pd.DataFrame(columns=SCHEDULE_COLUMNS)
    fixed, earliest = _freeze(original, start, interrupted)
    forced = {}
    for oid in interrupted:
        earliest[oid] = end
        forced[oid] = machine_id
    extra = pd.DataFrame([{"machine_id": machine_id, "start_minute": start,
                           "end_minute": end, "reason": "Simulated breakdown"}])
    updated = factory.replace(downtimes=pd.concat([factory.downtimes, extra], ignore_index=True))
    result = solve_schedule(updated, objective="stability", time_limit=time_limit, workers=workers,
                            fixed=fixed, earliest=earliest, forced_machine=forced,
                            history=history, baseline=original, use_hint=False)
    result.metadata = {"scenario": "breakdown", "decision_time": start, "machine_id": machine_id,
                       "breakdown_end": end, "fixed_operation_ids": sorted(fixed),
                       "interrupted_operation_ids": sorted(interrupted),
                       "directly_affected_operation_ids": sorted(overlaps.operation_id.tolist()),
                       "policy": "Interrupted operation is aborted; its full setup and processing restart on the same machine after repair."}
    _check_result(updated, result, fixed)
    return updated, result


def reschedule_urgent_order(factory: FactoryData, original: pd.DataFrame, *, now: int,
                            order_id: str, product_id: str, quantity: int, due: int,
                            priority: int = 5, time_limit: float = 10, workers: int = 4) -> tuple[FactoryData, ScheduleResult]:
    """Freeze completed/running operations and schedule a newly released order.

    The urgent order bypasses the aggregate materials planner; the user must
    confirm material availability separately.
    """
    _check_original(factory, original, now)
    if order_id in set(factory.orders.order_id):
        raise ValueError("Urgent order ID already exists")
    added = pd.DataFrame([{"order_id": order_id, "product_id": product_id, "quantity": quantity,
                           "release_minute": now, "due_minute": due, "priority": priority}])
    updated = factory.replace(orders=pd.concat([factory.orders, added], ignore_index=True))
    fixed, earliest = _freeze(original, now)
    result = solve_schedule(updated, objective="stability", time_limit=time_limit, workers=workers,
                            fixed=fixed, earliest=earliest, baseline=original, use_hint=False)
    result.metadata = {"scenario": "urgent_order", "decision_time": now, "urgent_order_id": order_id,
                       "fixed_operation_ids": sorted(fixed),
                       "policy": "Completed and running operations are frozen; the new order is released at the decision time."}
    _check_result(updated, result, fixed)
    return updated, result
