"""Metrics and comparisons computed directly from completed schedule rows."""
from __future__ import annotations
import pandas as pd
from .calendars import available_minutes
from .data_loader import FactoryData


def order_metrics(factory: FactoryData, schedule: pd.DataFrame) -> pd.DataFrame:
    cols = ["order_id", "product_id", "quantity", "priority", "due_minute"]
    orders = factory.orders[cols].copy()
    finish = schedule.groupby("order_id", as_index=False)["finish"].max().rename(columns={"finish": "completion_minute"})
    result = orders.merge(finish, how="left", on="order_id", validate="one_to_one")
    result["tardiness_minutes"] = (result.completion_minute - result.due_minute).clip(lower=0)
    result["weighted_tardiness"] = result.tardiness_minutes * result.priority
    result["late"] = result.tardiness_minutes > 0
    return result


def machine_workload(factory: FactoryData, schedule: pd.DataFrame, history: pd.DataFrame | None = None) -> pd.DataFrame:
    max_finish = int(schedule.finish.max()) if not schedule.empty else 0
    machines = factory.machines[["machine_id", "machine_name", "resource_group"]].copy()
    busy = schedule.assign(_busy=schedule.finish - schedule.start).groupby("machine_id")._busy.sum()
    if history is not None and not history.empty:
        wasted = history.assign(_busy=history.finish - history.start).groupby("machine_id")._busy.sum()
    else:
        wasted = pd.Series(dtype=float)
    machines["scheduled_busy_minutes"] = machines.machine_id.map(busy).fillna(0).astype(int)
    machines["aborted_busy_minutes"] = machines.machine_id.map(wasted).fillna(0).astype(int)
    machines["total_busy_minutes"] = machines.scheduled_busy_minutes + machines.aborted_busy_minutes
    machines["available_minutes_to_makespan"] = machines.machine_id.map(lambda m: available_minutes(factory, m, max_finish))
    machines["utilization"] = machines.apply(lambda r: r.total_busy_minutes / r.available_minutes_to_makespan if r.available_minutes_to_makespan else 0.0, axis=1)
    return machines


def summary_metrics(factory: FactoryData, schedule: pd.DataFrame, history: pd.DataFrame | None = None) -> dict:
    if schedule.empty:
        return {}
    orders = order_metrics(factory, schedule)
    if orders.completion_minute.isna().any():
        raise ValueError("Cannot compute complete-order metrics for an incomplete schedule")
    return {"makespan": int(schedule.finish.max()),
            "active_span": int(schedule.finish.max() - schedule.start.min()),
            "total_tardiness": int(orders.tardiness_minutes.sum()),
            "weighted_tardiness": int(orders.weighted_tardiness.sum()),
            "late_orders": int(orders.late.sum()),
            "order_count": int(len(orders)),
            "scheduled_busy_minutes": int((schedule.finish - schedule.start).sum()),
            "aborted_busy_minutes": int((history.finish - history.start).sum()) if history is not None and not history.empty else 0}


def compare_schedules(original_factory: FactoryData, original: pd.DataFrame,
                      revised_factory: FactoryData, revised: pd.DataFrame,
                      revised_history: pd.DataFrame | None = None) -> dict:
    before = order_metrics(original_factory, original)[["order_id", "completion_minute", "tardiness_minutes", "late"]]
    after = order_metrics(revised_factory, revised)[["order_id", "completion_minute", "tardiness_minutes", "late"]]
    orders = before.merge(after, how="outer", on="order_id", suffixes=("_original", "_revised"))
    orders["completion_change_minutes"] = orders.completion_minute_revised - orders.completion_minute_original
    orders["new_order"] = orders.completion_minute_original.isna()
    orders["newly_late"] = (~orders.new_order) & (orders.late_original == False) & (orders.late_revised == True)  # noqa: E712
    a = original[["operation_id", "order_id", "machine_id", "start", "finish"]]
    b = revised[["operation_id", "order_id", "machine_id", "start", "finish"]]
    operations = a.merge(b, how="outer", on="operation_id", suffixes=("_original", "_revised"))
    operations["order_id"] = operations.order_id_original.combine_first(operations.order_id_revised)
    operations = operations.drop(columns=["order_id_original", "order_id_revised"])
    operations["start_change_minutes"] = operations.start_revised - operations.start_original
    operations["machine_changed"] = operations.machine_id_original.notna() & operations.machine_id_revised.notna() & (operations.machine_id_original != operations.machine_id_revised)
    old_work = machine_workload(original_factory, original)[["machine_id", "scheduled_busy_minutes", "total_busy_minutes"]]
    new_work = machine_workload(revised_factory, revised, revised_history)[["machine_id", "scheduled_busy_minutes", "aborted_busy_minutes", "total_busy_minutes"]]
    machines = old_work.merge(new_work, on="machine_id", how="outer", suffixes=("_original", "_revised"))
    machines["total_busy_change_minutes"] = machines.total_busy_minutes_revised - machines.total_busy_minutes_original
    return {"orders": orders, "operations": operations, "machines": machines,
            "original": summary_metrics(original_factory, original),
            "revised": summary_metrics(revised_factory, revised, revised_history),
            "newly_late_orders": int(orders.newly_late.sum()),
            "machine_reassignments": int(operations.machine_changed.sum())}
