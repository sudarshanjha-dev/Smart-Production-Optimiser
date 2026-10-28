"""Flexible job-shop scheduling with CP-SAT, calendars and fixed per-operation setup."""
from __future__ import annotations
from dataclasses import dataclass, field
from time import perf_counter
import pandas as pd
from ortools.sat.python import cp_model
from .calendars import blocked_windows
from .data_loader import FactoryData, build_operations, schedule_row

SCHEDULE_COLUMNS = ["operation_id", "order_id", "product_id", "operation_sequence", "operation_name",
                    "predecessor_operation_id", "quantity", "machine_id", "start", "finish",
                    "setup_minutes", "processing_minutes", "release_minute", "due_minute", "priority", "segment_type"]

@dataclass
class ScheduleResult:
    status: str
    schedule: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=SCHEDULE_COLUMNS))
    objective: str = ""
    objective_value: float | None = None
    best_bound: float | None = None
    solve_seconds: float = 0.0
    message: str = ""
    history: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=SCHEDULE_COLUMNS))
    metadata: dict = field(default_factory=dict)

    @property
    def has_schedule(self) -> bool:
        return self.status in {"OPTIMAL", "FEASIBLE", "HEURISTIC"}


def solve_schedule(factory: FactoryData, objective: str = "makespan", time_limit: float = 10,
                   workers: int = 4, *, fixed: dict[str, dict] | None = None,
                   earliest: dict[str, int] | None = None, forced_machine: dict[str, str] | None = None,
                   history: pd.DataFrame | None = None, baseline: pd.DataFrame | None = None,
                   use_hint: bool = True) -> ScheduleResult:
    """Solve the full non-preemptive FJSP.

    For rescheduling, `fixed` pins actual completed/running operations; `earliest`
    imposes the decision/repair time, `forced_machine` fixes an aborted restart,
    and history blocks already-consumed time. Stability minimizes 10 times
    weighted tardiness + absolute start shifts + 120 minutes per reassignment.
    Only a returned OPTIMAL status proves the stated objective optimal.
    """
    if objective not in {"makespan", "weighted_tardiness", "stability"}:
        raise ValueError("Unknown scheduling objective")
    if time_limit <= 0 or workers < 1:
        raise ValueError("time_limit and workers must be positive")
    operations = build_operations(factory)
    if not operations:
        return ScheduleResult("NO_ORDERS", objective=objective, message="No positive-quantity orders to schedule.")
    fixed, earliest, forced_machine = fixed or {}, earliest or {}, forced_machine or {}
    history = history.copy() if history is not None else pd.DataFrame(columns=SCHEDULE_COLUMNS)
    if objective == "stability" and baseline is None:
        raise ValueError("The stability objective requires a previous schedule")
    H = factory.horizon
    model = cp_model.CpModel()
    starts, ends, presence, op_vars = {}, {}, {}, {}
    intervals: dict[str, list] = {m: [] for m in factory.machines.machine_id}

    for op in operations:
        start = model.NewIntVar(0, H, f"start[{op.operation_id}]")
        end = model.NewIntVar(0, H, f"finish[{op.operation_id}]")
        starts[op.operation_id], ends[op.operation_id] = start, end
        choices = []
        for alt in op.alternatives:
            assigned = model.NewBoolVar(f"assign[{op.operation_id},{alt.machine_id}]")
            interval = model.NewOptionalIntervalVar(start, alt.duration(op.quantity), end, assigned,
                                                    f"interval[{op.operation_id},{alt.machine_id}]")
            presence[(op.operation_id, alt.machine_id)] = assigned
            choices.append(assigned)
            intervals[alt.machine_id].append(interval)
        model.AddExactlyOne(choices)
        model.Add(start >= op.release)
        if op.operation_id in earliest:
            model.Add(start >= int(earliest[op.operation_id]))
        if op.operation_id in fixed:
            f = fixed[op.operation_id]
            model.Add(start == int(f["start"]))
            model.Add(end == int(f["finish"]))
            machine = str(f["machine_id"])
            if (op.operation_id, machine) not in presence:
                raise ValueError(f"Fixed operation {op.operation_id} uses ineligible machine {machine}")
            model.Add(presence[(op.operation_id, machine)] == 1)
        if op.operation_id in forced_machine:
            machine = forced_machine[op.operation_id]
            if (op.operation_id, machine) not in presence:
                raise ValueError(f"Forced operation {op.operation_id} uses ineligible machine {machine}")
            model.Add(presence[(op.operation_id, machine)] == 1)
        op_vars[op.operation_id] = op
    for op in operations:
        if op.predecessor_id:
            model.Add(starts[op.operation_id] >= ends[op.predecessor_id])
    for machine_id in intervals:
        extras = [(int(row.start), int(row.finish)) for row in history.itertuples(index=False) if row.machine_id == machine_id]
        for i, (a, b) in enumerate(blocked_windows(factory, machine_id, extras)):
            intervals[machine_id].append(model.NewIntervalVar(a, b - a, b, f"blocked[{machine_id},{i}]"))
        model.AddNoOverlap(intervals[machine_id])

    last = {}
    for op in operations:
        last[op.order_id] = op  # operations sorted by sequence within order
    completion_vars = [ends[op.operation_id] for op in last.values()]
    makespan = model.NewIntVar(0, H, "makespan")
    model.AddMaxEquality(makespan, completion_vars)
    tardiness_vars = []
    for op in last.values():
        t = model.NewIntVar(0, H, f"tardiness[{op.order_id}]")
        model.AddMaxEquality(t, [ends[op.operation_id] - op.due, 0])
        tardiness_vars.append(op.priority * t)
    weighted_tardiness = sum(tardiness_vars)
    if objective == "makespan":
        model.Minimize(makespan)
    elif objective == "weighted_tardiness":
        # A 1-minute improvement in weighted tardiness dominates any makespan change.
        model.Minimize((H + 1) * weighted_tardiness + makespan)
    else:
        previous = {str(x.operation_id): x for x in baseline.itertuples(index=False)}
        shifts, changes = [], []
        for op in operations:
            old = previous.get(op.operation_id)
            if old is None:
                continue
            delta = model.NewIntVar(0, H, f"start_shift[{op.operation_id}]")
            model.AddAbsEquality(delta, starts[op.operation_id] - int(old.start))
            shifts.append(delta)
            if (op.operation_id, str(old.machine_id)) in presence:
                changes.append(1 - presence[(op.operation_id, str(old.machine_id))])
            else:
                changes.append(1)
        model.Minimize(10 * weighted_tardiness + sum(shifts) + 120 * sum(changes))

    # A valid greedy schedule is a complete hint, not a hard constraint or a claim of optimality.
    if use_hint and not fixed and not earliest and not forced_machine and history.empty:
        from .dispatching_rules import dispatch_schedule
        greedy = dispatch_schedule(factory, "EDD")
        if greedy.has_schedule:
            hint = {r.operation_id: r for r in greedy.schedule.itertuples(index=False)}
            for op in operations:
                row = hint[op.operation_id]
                model.AddHint(starts[op.operation_id], int(row.start))
                model.AddHint(ends[op.operation_id], int(row.finish))
                for alt in op.alternatives:
                    model.AddHint(presence[(op.operation_id, alt.machine_id)], int(row.machine_id == alt.machine_id))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit)
    solver.parameters.num_search_workers = int(workers)
    solver.parameters.random_seed = 41
    start_clock = perf_counter()
    status_code = solver.Solve(model)
    elapsed = perf_counter() - start_clock
    status = solver.StatusName(status_code)
    if status_code not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return ScheduleResult(status, objective=objective, solve_seconds=elapsed, history=history,
                              message="No schedule was returned. INFEASIBLE is a proof; UNKNOWN is not.")
    rows = []
    for op in operations:
        alt = next(a for a in op.alternatives if solver.Value(presence[(op.operation_id, a.machine_id)]) == 1)
        rows.append(schedule_row(op, alt, solver.Value(starts[op.operation_id])))
    schedule = pd.DataFrame(rows, columns=SCHEDULE_COLUMNS).sort_values(["machine_id", "start", "operation_id"]).reset_index(drop=True)
    return ScheduleResult(status, schedule, objective, float(solver.ObjectiveValue()), float(solver.BestObjectiveBound()),
                          elapsed, "OPTIMAL is proven; FEASIBLE is an incumbent without a proof.", history)
