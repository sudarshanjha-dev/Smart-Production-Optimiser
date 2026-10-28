"""A before-execution what-if: extend one machine's daily working hours."""
from __future__ import annotations
from .calendars import available_minutes
from .data_loader import FactoryData
from .schedule_metrics import summary_metrics


def extend_machine_shift(factory: FactoryData, machine_id: str, new_end: int) -> tuple[FactoryData, int]:
    if machine_id not in set(factory.machines.machine_id):
        raise ValueError("Unknown machine")
    machines = factory.machines.copy()
    mask = machines.machine_id == machine_id
    old_end = int(machines.loc[mask, 'shift_end_minute'].iloc[0])
    if not isinstance(new_end, int) or not old_end < new_end <= 1440:
        raise ValueError("New shift end must be later than the existing end and at most midnight")
    machines.loc[mask, 'shift_end_minute'] = new_end
    updated = factory.replace(machines=machines)
    extra_minutes = available_minutes(updated, machine_id) - available_minutes(factory, machine_id)
    return updated, extra_minutes


def cost_estimate(original_factory, original_schedule, expanded_factory, expanded_schedule,
                  extra_available_minutes: int, cost_per_extra_hour: float, cost_per_weighted_tardy_minute: float) -> dict:
    if cost_per_extra_hour < 0 or cost_per_weighted_tardy_minute < 0:
        raise ValueError("Cost rates cannot be negative")
    old = summary_metrics(original_factory, original_schedule)
    new = summary_metrics(expanded_factory, expanded_schedule)
    extra_cost = extra_available_minutes / 60 * cost_per_extra_hour
    delay_savings = (old['weighted_tardiness'] - new['weighted_tardiness']) * cost_per_weighted_tardy_minute
    return {"extra_available_minutes": extra_available_minutes, "estimated_extra_capacity_cost": extra_cost,
            "estimated_delay_cost_saving": delay_savings, "estimated_net_value": delay_savings - extra_cost,
            "original_makespan": old['makespan'], "expanded_makespan": new['makespan'],
            "original_weighted_tardiness": old['weighted_tardiness'], "expanded_weighted_tardiness": new['weighted_tardiness']}
