"""Validated, source-unit textile metrics and equal-constraint comparisons."""
from __future__ import annotations
import pandas as pd
from .textile_data import INPUT_SHA256, TextileInstance
from .textile_validation import validate_textile_schedule


def textile_metrics(instance: TextileInstance, schedule: pd.DataFrame) -> dict:
    errors = validate_textile_schedule(instance, schedule)
    if errors: raise ValueError("Cannot calculate KPIs for invalid schedule: " + "; ".join(errors[:4]))
    makespan = int(schedule.end_slot.max())
    loads = [0.0] * instance.horizon
    for row in schedule.itertuples(index=False):
        for offset, value in enumerate(instance.modes[row.mode_id].power):
            loads[int(row.start_slot) + offset] += value
    solar_used = sum(min(load, solar) for load, solar in zip(loads, instance.solar_availability))
    grid = [max(0.0, load - solar) for load, solar in zip(loads, instance.solar_availability)]
    score = sum(consumption * price for consumption, price in zip(grid, instance.grid_prices))
    deadline_units = {op.unit_id for op in instance.operations if op.deadline is not None}
    return {"operations": len(schedule), "product_units": len({o.unit_id for o in instance.operations}),
            "makespan_slots": makespan, "makespan_working_minutes": makespan * 5,
            "calendar_elapsed_minutes": (makespan * 5 + sum(480 for leap in instance.time_leaps if leap < makespan))
                if instance.input_hash == INPUT_SHA256 else None,
            "total_profile_raw": sum(loads), "solar_used_raw": solar_used,
            "grid_draw_raw": sum(grid), "source_style_cost_score": score,
            "deadline_units": len(deadline_units), "deadline_units_on_time": len(deadline_units),
            "mean_machine_utilization_pct": 100 * float(schedule.duration_slots.sum()) / (len(instance.machines) * makespan)}


def textile_machine_metrics(instance: TextileInstance, schedule: pd.DataFrame) -> pd.DataFrame:
    info = textile_metrics(instance, schedule)
    span = info["makespan_slots"]
    rows = []
    for machine in instance.machines:
        subset = schedule[schedule.machine_id == machine]
        busy = int(subset.duration_slots.sum())
        rows.append({"machine_id": machine, "tasks": len(subset), "busy_slots": busy,
                     "busy_minutes": busy * 5, "utilization_pct": 100 * busy / span})
    return pd.DataFrame(rows)


def compare_textile(instance: TextileInstance, baseline: pd.DataFrame, candidate: pd.DataFrame) -> pd.DataFrame:
    """Both schedules must independently validate against the same instance."""
    b, c = textile_metrics(instance, baseline), textile_metrics(instance, candidate)
    columns = [("Makespan (working slots)", "makespan_slots"),
               ("Makespan (working minutes)", "makespan_working_minutes"),
               ("Total mode profile (raw)", "total_profile_raw"),
               ("Solar used (raw)", "solar_used_raw"),
               ("Grid draw (raw)", "grid_draw_raw"),
               ("Source-style cost score", "source_style_cost_score"),
               ("Mean machine utilization (%)", "mean_machine_utilization_pct")]
    result = []
    for label, key in columns:
        baseline_value, candidate_value = b[key], c[key]
        # Positive means the candidate is lower; no assertion that lower is better
        # for solar use or utilization, so percentage is intentionally blank there.
        smaller_is_better = key not in {"solar_used_raw", "mean_machine_utilization_pct"}
        pct = (100 * (baseline_value - candidate_value) / baseline_value
               if smaller_is_better and baseline_value else None)
        result.append({"metric": label, "baseline": baseline_value, "optimized": candidate_value,
                       "reduction_pct": pct})
    return pd.DataFrame(result)
