"""Flexible task/machine CP-SAT scheduling for the validated textile input."""
from __future__ import annotations
from time import perf_counter
import pandas as pd
from ortools.sat.python import cp_model
from .scheduling_model import ScheduleResult
from .textile_data import TextileInstance
from .textile_dispatching import dispatch_textile, textile_row
from .textile_validation import TEXTILE_COLUMNS, validate_textile_schedule


def solve_textile(instance: TextileInstance, time_limit: float = 10.0, workers: int = 1,
                  baseline: ScheduleResult | None = None, seed: int = 0,
                  objective: str = "makespan", makespan_limit: int | None = None) -> ScheduleResult:
    """Minimize Cmax, or total raw mode-profile sum subject to a Cmax cap.

    Machine/mode alternatives use optional intervals; unit intervals enforce
    non-overlap when that policy is selected. Time leaps are forbidden crossing points. Collision is
    cross-task in the single cell. A validated baseline and separately generated
    load-balanced dispatch candidates are considered as warm-start hints, never
    a hard bound or an unlabelled solution fallback.
    """
    if time_limit <= 0 or workers < 1:
        raise ValueError("time_limit and workers must be positive")
    if objective not in {"makespan", "profile"}:
        raise ValueError("objective must be makespan or profile")
    task_counts = {task: sum(op.task == task for op in instance.operations) for task in instance.task_modes}
    collision_pairs = sum(task_counts[a] * task_counts[b] for a, b in instance.collision_pairs)
    if collision_pairs > 100_000:
        raise ValueError("Textile collision expansion exceeds the supported 100,000 cross-task pairs; "
                         "no collision constraint was skipped")
    if objective == "profile" and (isinstance(makespan_limit, bool) or not isinstance(makespan_limit, int)
                                    or not 1 <= makespan_limit <= instance.horizon):
        raise ValueError("A profile objective requires an integer makespan_limit within the horizon")
    objective_name = "makespan_slots" if objective == "makespan" else "total_mode_profile_raw"
    profile_scale = 1000
    profile_costs = {}
    if objective == "profile":
        # CP-SAT is integer-only. Refuse rather than silently round an upload
        # whose mode values have more than three decimal places.
        for mode_id, mode in instance.modes.items():
            scaled = [round(value * profile_scale) for value in mode.power]
            if any(abs(value * profile_scale - rounded) > 1e-7 for value, rounded in zip(mode.power, scaled)):
                raise ValueError("Profile objective supports at most three exact decimal places per power value")
            profile_costs[mode_id] = sum(scaled)
        maximum_total = sum(max(profile_costs[c.mode_id] for c in op.choices) for op in instance.operations)
        if maximum_total >= 2**62: raise ValueError("Profile objective exceeds CP-SAT's safe integer range")
    clock = perf_counter()
    if baseline is None: baseline = dispatch_textile(instance)
    candidates = [baseline] if baseline.has_schedule else []
    if baseline.has_schedule:
        errors = validate_textile_schedule(instance, baseline.schedule)
        if errors: raise ValueError("Refusing invalid CP-SAT hint: " + "; ".join(errors[:3]))
    # The benchmark remains the unbiased deadline-FIFO dispatch. Separately,
    # try four explicitly load-balanced, fully validated dispatches and give the
    # best as a hint. CP-SAT must still return and validate its own solution.
    # Skip multi-start for large uploads to cap preprocessing cost.
    if len(instance.operations) <= 500:
        for bias in (0.75, 1.0, 1.5, 2.0):
            trial = dispatch_textile(instance, load_bias=bias)
            if trial.has_schedule: candidates.append(trial)
    if objective == "profile":
        candidates = [result for result in candidates if int(result.schedule.end_slot.max()) <= makespan_limit]
        warm = (min(candidates, key=lambda result: sum(profile_costs[mode] for mode in result.schedule.mode_id))
                if candidates else None)
    else:
        warm = min(candidates, key=lambda result: int(result.schedule.end_slot.max())) if candidates else None
    hint = ({row.operation_id: row for row in warm.schedule.itertuples(index=False)} if warm is not None else {})

    model = cp_model.CpModel()
    H = instance.horizon
    starts, ends, sizes, presence = {}, {}, {}, {}
    machines: dict[str, list] = {m: [] for m in instance.machines}
    units: dict[str, list] = {}
    by_task: dict[str, list] = {}
    for op in instance.operations:
        oid = op.operation_id
        s = model.NewIntVar(0, H, f"start[{oid}]")
        e = model.NewIntVar(0, H, f"end[{oid}]")
        size = model.NewIntVar(min(c.duration for c in op.choices), max(c.duration for c in op.choices), f"duration[{oid}]")
        starts[oid], ends[oid], sizes[oid] = s, e, size
        whole = model.NewIntervalVar(s, size, e, f"unit_interval[{oid}]")
        units.setdefault(op.unit_id, []).append(whole)
        by_task.setdefault(op.task, []).append(op)
        assigned_list = []
        for index, choice in enumerate(op.choices):
            assigned = model.NewBoolVar(f"assign[{oid},{choice.machine_id},{choice.mode_id}]")
            presence[(oid, index)] = assigned; assigned_list.append(assigned)
            interval = model.NewOptionalIntervalVar(s, choice.duration, e, assigned,
                                                    f"machine_interval[{oid},{choice.machine_id},{choice.mode_id}]")
            machines[choice.machine_id].append(interval)
            model.Add(size == choice.duration).OnlyEnforceIf(assigned)
            legal_starts = [[a, b - choice.duration] for a, b in instance.windows if b - a >= choice.duration]
            if legal_starts:
                model.AddLinearExpressionInDomain(s, cp_model.Domain.FromIntervals(legal_starts)).OnlyEnforceIf(assigned)
            else:
                model.Add(assigned == 0)
        model.AddExactlyOne(assigned_list)
        if op.deadline is not None: model.Add(e <= op.deadline)
        if oid in hint:
            row = hint[oid]
            model.AddHint(s, int(row.start_slot)); model.AddHint(e, int(row.end_slot)); model.AddHint(size, int(row.duration_slots))
            for index, choice in enumerate(op.choices):
                model.AddHint(presence[(oid, index)], int(row.machine_id == choice.machine_id and row.mode_id == choice.mode_id))
    for op in instance.operations:
        for pred in op.predecessors: model.Add(ends[pred] <= starts[op.operation_id])
        if op.symmetry_predecessor is not None:
            model.Add(starts[op.symmetry_predecessor] <= starts[op.operation_id])
    for intervals in machines.values(): model.AddNoOverlap(intervals)
    if instance.unit_exclusive:
        for intervals in units.values(): model.AddNoOverlap(intervals)
    for task1, task2 in instance.collision_pairs:
        # Only forbid X against Y, not X against X or Y against Y.
        for a in by_task.get(task1, []):
            for b in by_task.get(task2, []):
                before = model.NewBoolVar(f"collision[{a.operation_id},{b.operation_id}]")
                model.Add(ends[a.operation_id] <= starts[b.operation_id]).OnlyEnforceIf(before)
                model.Add(ends[b.operation_id] <= starts[a.operation_id]).OnlyEnforceIf(before.Not())
                if a.operation_id in hint and b.operation_id in hint:
                    model.AddHint(before, int(hint[a.operation_id].end_slot <= hint[b.operation_id].start_slot))
    makespan = model.NewIntVar(0, H, "makespan")
    model.AddMaxEquality(makespan, list(ends.values()))
    if objective == "makespan":
        model.Minimize(makespan)
    else:
        model.Add(makespan <= makespan_limit)
        model.Minimize(sum(profile_costs[choice.mode_id] * presence[(op.operation_id, i)]
                           for op in instance.operations for i, choice in enumerate(op.choices)))
    if hint: model.AddHint(makespan, max(int(row.end_slot) for row in hint.values()))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit)
    solver.parameters.num_search_workers = int(workers)
    solver.parameters.random_seed = int(seed)
    status_code = solver.Solve(model)
    status = solver.StatusName(status_code)
    seconds = perf_counter() - clock
    meta = {"solver_wall_seconds": solver.WallTime(), "time_limit_seconds": float(time_limit),
            "workers": int(workers), "random_seed": int(seed), "order_interpretation": instance.order_interpretation,
            "unit_exclusive": instance.unit_exclusive, "input_sha256": instance.input_hash,
            "warm_start_source": warm.message if warm is not None else "none",
            "warm_start_makespan_slots": int(warm.schedule.end_slot.max()) if warm is not None else None,
            "objective": objective_name, "makespan_limit_slots": makespan_limit if objective == "profile" else None,
            "profile_integer_scale": profile_scale if objective == "profile" else None}
    if status not in {"FEASIBLE", "OPTIMAL"}:
        messages = {"INFEASIBLE": "CP-SAT proved the formulated model infeasible.",
                    "UNKNOWN": "No feasible solution was returned within the search limit; infeasibility is not established.",
                    "MODEL_INVALID": "CP-SAT rejected the formulation."}
        return ScheduleResult(status, objective=objective_name, solve_seconds=seconds,
                              message=messages.get(status, "No schedule returned."), metadata=meta)
    rows = []
    for op in instance.operations:
        index = next(i for i in range(len(op.choices)) if solver.Value(presence[(op.operation_id, i)]))
        rows.append(textile_row(op, op.choices[index], solver.Value(starts[op.operation_id])))
    schedule = pd.DataFrame(rows, columns=TEXTILE_COLUMNS).sort_values(["machine_id", "start_slot", "operation_id"]).reset_index(drop=True)
    errors = validate_textile_schedule(instance, schedule, makespan_limit=makespan_limit if objective == "profile" else None)
    if errors: raise RuntimeError("Invalid CP-SAT textile schedule: " + "; ".join(errors[:5]))
    scale = 1 if objective == "makespan" else profile_scale
    return ScheduleResult(status, schedule=schedule, objective=objective_name, objective_value=solver.ObjectiveValue() / scale,
                          best_bound=solver.BestObjectiveBound() / scale, solve_seconds=seconds,
                          message="Only OPTIMAL proves the stated objective optimum." if status == "FEASIBLE" else
                                  "CP-SAT proved the stated objective optimum.", metadata=meta)
