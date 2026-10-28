"""Aggregate integer quantity planning, deliberately separate from detailed scheduling."""
from __future__ import annotations
from dataclasses import dataclass, field
import math
import pandas as pd
import pulp
from .calendars import available_minutes
from .data_loader import FactoryData, build_operations

@dataclass
class PlanningResult:
    status: str
    order_plan: pd.DataFrame = field(default_factory=pd.DataFrame)
    capacity: pd.DataFrame = field(default_factory=pd.DataFrame)
    objective_value: float | None = None
    material_used: int = 0
    material_limit: int = 0
    message: str = ""

    @property
    def has_plan(self) -> bool:
        return self.status == "OPTIMAL"


def plan_production(factory: FactoryData, material_limit: int, capacity_factor: float = 1.0) -> PlanningResult:
    """Minimize production cost + priority-weighted unmet-demand penalty.

    Capacity uses the sum of machine working minutes by resource group. Each
    operation contributes the minimum per-unit processing and minimum fixed
    setup among eligible machines (an optimistic aggregate lower bound).
    It ignores sequencing, daily fragmentation and due dates. A plan is NOT a
    guarantee of detailed schedule feasibility.
    """
    if not isinstance(material_limit, int) or not 0 <= material_limit <= 10_000_000:
        raise ValueError("Material limit must be a nonnegative integer <= 10,000,000")
    if not math.isfinite(capacity_factor) or not 0 < capacity_factor <= 1:
        raise ValueError("Capacity factor must be greater than 0 and no greater than 1")
    if factory.orders.empty:
        return PlanningResult("NO_ORDERS", message="No demand to plan.")
    model = pulp.LpProblem("aggregate_production_quantity_plan", pulp.LpMinimize)
    orders = list(factory.orders.itertuples(index=False))
    products = factory.products.set_index("product_id").to_dict("index")
    groups = factory.machines.set_index("machine_id").resource_group.to_dict()
    capacities = {group: sum(available_minutes(factory, m) for m in ms.machine_id) * capacity_factor
                  for group, ms in factory.machines.groupby("resource_group")}
    qty, used = {}, {}
    for i, order in enumerate(orders):
        qty[order.order_id] = pulp.LpVariable(f"qty_{i}", lowBound=0, upBound=order.quantity, cat="Integer")
        used[order.order_id] = pulp.LpVariable(f"used_{i}", cat="Binary")
        model += qty[order.order_id] <= order.quantity * used[order.order_id]
        model += qty[order.order_id] >= used[order.order_id]
    material_expr = pulp.lpSum(qty[o.order_id] * products[o.product_id]["material_per_unit"] for o in orders)
    model += material_expr <= material_limit, "material_limit"
    group_terms: dict[str, list] = {g: [] for g in capacities}
    for op in build_operations(factory):
        group = groups[op.alternatives[0].machine_id]
        group_terms[group].append(min(a.minutes_per_unit for a in op.alternatives) * qty[op.order_id] +
                                  min(a.setup_minutes for a in op.alternatives) * used[op.order_id])
    for idx, group in enumerate(capacities):
        model += pulp.lpSum(group_terms[group]) <= capacities[group], f"group_capacity_{idx}"
    model += pulp.lpSum(products[o.product_id]["unit_cost"] * qty[o.order_id] +
                        products[o.product_id]["shortage_penalty"] * o.priority * (o.quantity - qty[o.order_id])
                        for o in orders)
    try:
        model.solve(pulp.PULP_CBC_CMD(msg=False))
    except pulp.PulpSolverError as exc:
        return PlanningResult("SOLVER_ERROR", message=f"CBC could not run: {exc}")
    # No time limit is imposed; require an actual proven-optimal integer solution.
    if model.status != pulp.LpStatusOptimal or model.sol_status != pulp.LpSolutionOptimal:
        return PlanningResult(pulp.LpStatus.get(model.status, "UNKNOWN").upper(), message="No proven-optimal plan returned.")
    rows = []
    for o in orders:
        planned = int(round(pulp.value(qty[o.order_id])))
        p = products[o.product_id]
        rows.append({"order_id": o.order_id, "product_id": o.product_id, "priority": o.priority,
                     "demand_quantity": int(o.quantity), "planned_quantity": planned, "shortage_quantity": int(o.quantity - planned),
                     "material_used": int(planned * p["material_per_unit"]),
                     "production_cost": planned * p["unit_cost"],
                     "shortage_penalty_cost": (o.quantity - planned) * p["shortage_penalty"] * o.priority})
    plan = pd.DataFrame(rows)
    cap_rows = []
    for group in sorted(capacities):
        value = pulp.value(pulp.lpSum(group_terms[group]))
        cap_rows.append({"resource_group": group, "available_minutes": float(capacities[group]),
                         "optimistic_load_minutes": float(value or 0),
                         "slack_minutes": float(capacities[group] - (value or 0))})
    return PlanningResult("OPTIMAL", plan, pd.DataFrame(cap_rows), float(pulp.value(model.objective)),
                          int(plan.material_used.sum()), material_limit,
                          "Aggregate lower-bound capacity; detailed scheduling must still be solved and validated.")


def factory_from_plan(factory: FactoryData, result: PlanningResult) -> FactoryData:
    """Replace order quantities with the plan; zero-production orders are omitted."""
    if not result.has_plan:
        raise ValueError("Only a proven-optimal plan can be passed to scheduling")
    required = {"order_id", "planned_quantity"}
    if required - set(result.order_plan.columns) or result.order_plan.order_id.duplicated().any():
        raise ValueError("Plan must contain each order exactly once")
    merged = factory.orders.merge(result.order_plan[["order_id", "planned_quantity"]], on="order_id", how="left", validate="one_to_one")
    if merged.planned_quantity.isna().any() or len(result.order_plan) != len(factory.orders):
        raise ValueError("Plan and original orders do not match")
    if any(float(x) != int(x) for x in merged.planned_quantity) or ((merged.planned_quantity < 0) | (merged.planned_quantity > merged.quantity)).any():
        raise ValueError("Planned quantities must be integers within the demand bounds")
    merged["quantity"] = merged.planned_quantity.astype(int)
    return factory.replace(orders=merged.loc[merged.quantity > 0, factory.orders.columns].reset_index(drop=True))
