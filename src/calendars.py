"""Half-open integer-minute shift, maintenance and outage interval helpers."""
from __future__ import annotations
from .data_loader import FactoryData

Interval = tuple[int, int]


def merge_intervals(intervals: list[Interval]) -> list[Interval]:
    result: list[Interval] = []
    for a, b in sorted((int(a), int(b)) for a, b in intervals if a < b):
        if result and a <= result[-1][1]:
            result[-1] = (result[-1][0], max(result[-1][1], b))
        else:
            result.append((a, b))
    return result


def subtract_intervals(base: list[Interval], blocked: list[Interval]) -> list[Interval]:
    blocks = merge_intervals(blocked)
    result = []
    for a, b in merge_intervals(base):
        cursor = a
        for x, y in blocks:
            if y <= cursor: continue
            if x >= b: break
            if x > cursor: result.append((cursor, min(x, b)))
            cursor = max(cursor, y)
            if cursor >= b: break
        if cursor < b: result.append((cursor, b))
    return result


def machine_windows(factory: FactoryData, machine_id: str, extra_blocked: list[Interval] | None = None) -> list[Interval]:
    """Available intervals inside [0,horizon), excluding all configured downtime."""
    machine = factory.machines.set_index("machine_id").loc[machine_id]
    days = {int(x) for x in machine.working_days.split("|")}
    shifts = []
    for day in range((factory.horizon + 1439) // 1440):
        if (factory.origin.weekday() + day) % 7 in days:
            a = day * 1440 + int(machine.shift_start_minute)
            b = min(factory.horizon, day * 1440 + int(machine.shift_end_minute))
            if a < b and a < factory.horizon:
                shifts.append((a, b))
    downtime = [(int(x.start_minute), int(x.end_minute)) for x in factory.downtimes.itertuples(index=False) if x.machine_id == machine_id]
    return subtract_intervals(shifts, downtime + (extra_blocked or []))


def blocked_windows(factory: FactoryData, machine_id: str, extra_blocked: list[Interval] | None = None) -> list[Interval]:
    return subtract_intervals([(0, factory.horizon)], machine_windows(factory, machine_id, extra_blocked))


def available_minutes(factory: FactoryData, machine_id: str, end: int | None = None) -> int:
    stop = factory.horizon if end is None else max(0, min(end, factory.horizon))
    return sum(max(0, min(b, stop) - a) for a, b in machine_windows(factory, machine_id) if a < stop)


def first_fit(windows: list[Interval], busy: list[Interval], earliest: int, duration: int) -> int | None:
    for a, b in subtract_intervals(windows, busy):
        start = max(a, earliest)
        if start + duration <= b:
            return start
    return None
