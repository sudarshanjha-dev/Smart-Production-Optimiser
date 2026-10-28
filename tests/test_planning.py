from src.production_planning import plan_production, factory_from_plan
from src.scheduling_model import solve_schedule
from src.schedule_validator import validate_schedule


def test_shortage_prioritization_and_integration(tiny_factory):
    plan = plan_production(tiny_factory, material_limit=1)
    assert plan.status == 'OPTIMAL'
    rows = plan.order_plan.set_index('order_id')
    assert rows.loc['J1', 'planned_quantity'] == 0
    assert rows.loc['J2', 'planned_quantity'] == 1
    assert rows.shortage_quantity.sum() == 1
    assert plan.objective_value == 21  # 1 production + 20 weighted shortage
    f = factory_from_plan(tiny_factory, plan)
    assert list(f.orders.order_id) == ['J2']
    s = solve_schedule(f, time_limit=5, workers=1)
    assert s.status == 'OPTIMAL' and len(s.schedule) == 2
    assert validate_schedule(f, s.schedule) == []


def test_aggregate_plan_does_not_prove_scheduling_feasibility(tiny_factory):
    # Aggregate work fits each separate resource, but each job's 2+3 minute
    # precedence chain cannot fit in the four-minute overall horizon.
    f = tiny_factory.replace(horizon=4)
    plan = plan_production(f, material_limit=1)
    assert plan.status == 'OPTIMAL' and plan.order_plan.planned_quantity.sum() == 1
    schedule = solve_schedule(factory_from_plan(f, plan), time_limit=5, workers=1)
    assert schedule.status == 'INFEASIBLE'


def test_zero_material_can_produce_empty_schedule_scope(tiny_factory):
    plan = plan_production(tiny_factory, 0)
    assert plan.status == 'OPTIMAL'
    f = factory_from_plan(tiny_factory, plan)
    assert f.orders.empty
    assert solve_schedule(f).status == 'NO_ORDERS'


def test_planned_batch_size_controls_processing_time(tiny_factory):
    orders = tiny_factory.orders.copy()
    orders.loc[orders.order_id == 'J2', 'quantity'] = 3
    f = tiny_factory.replace(orders=orders)
    plan = plan_production(f, material_limit=2)
    assert plan.status == 'OPTIMAL'
    assert plan.order_plan.set_index('order_id').loc['J2', 'planned_quantity'] == 2
    integrated = factory_from_plan(f, plan)
    result = solve_schedule(integrated, time_limit=5, workers=1)
    assert result.status == 'OPTIMAL'
    assert result.schedule.loc[result.schedule.machine_id == 'A', 'processing_minutes'].iloc[0] == 4
    assert result.schedule.loc[result.schedule.machine_id == 'B', 'processing_minutes'].iloc[0] == 6
