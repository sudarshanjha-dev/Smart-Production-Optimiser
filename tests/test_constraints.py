import pandas as pd
import pytest
from src.calendars import available_minutes
from src.capacity_analysis import extend_machine_shift
from src.data_loader import InputError
from src.schedule_validator import validate_schedule
from src.scheduling_model import solve_schedule


def test_fixed_setup_occupies_machine_and_increases_duration(tiny_factory):
    route = tiny_factory.routings.copy()
    route.loc[route.machine_id == 'A', 'setup_minutes'] = 2
    route.loc[route.machine_id == 'B', 'setup_minutes'] = 1
    f = tiny_factory.replace(routings=route)
    r = solve_schedule(f, time_limit=5, workers=1)
    assert r.status == 'OPTIMAL' and r.schedule.finish.max() == 12
    assert (r.schedule.finish - r.schedule.start == r.schedule.setup_minutes + r.schedule.processing_minutes).all()
    assert validate_schedule(f, r.schedule) == []
    changed = r.schedule.copy()
    changed.loc[changed.index[0], 'setup_minutes'] += 1
    assert any('setup or duration' in x for x in validate_schedule(f, changed))


def test_machine_eligibility_alternatives_and_downtime(tiny_factory):
    f = tiny_factory.replace(orders=tiny_factory.orders.iloc[:1])
    machines = pd.concat([f.machines, pd.DataFrame([['A2', 'A2', 'CUT', 0, 1440, '0|1|2|3|4|5|6']], columns=f.machines.columns)], ignore_index=True)
    routes = pd.concat([f.routings, pd.DataFrame([['P', 1, 'Cut', 'A2', 1, 0]], columns=f.routings.columns)], ignore_index=True)
    f = f.replace(machines=machines, routings=routes)
    fast = solve_schedule(f, time_limit=5, workers=1)
    assert fast.status == 'OPTIMAL' and fast.schedule.finish.max() == 4
    assert fast.schedule.loc[fast.schedule.operation_sequence == 1, 'machine_id'].iloc[0] == 'A2'
    outages = pd.DataFrame([['A2', 0, 5, 'Maintenance']], columns=['machine_id','start_minute','end_minute','reason'])
    f2 = f.replace(downtimes=outages)
    maintenance = solve_schedule(f2, time_limit=5, workers=1)
    assert maintenance.status == 'OPTIMAL' and maintenance.schedule.finish.max() == 5
    assert maintenance.schedule.loc[maintenance.schedule.operation_sequence == 1, 'machine_id'].iloc[0] == 'A'
    assert validate_schedule(f2, maintenance.schedule) == []


def test_calendar_shift_and_overlap_validation(tiny_factory):
    f = tiny_factory.replace(orders=tiny_factory.orders.iloc[:1])
    machines = f.machines.copy(); machines.loc[machines.machine_id == 'A', ['shift_start_minute', 'shift_end_minute']] = [4, 10]
    f = f.replace(machines=machines)
    r = solve_schedule(f, time_limit=5, workers=1)
    assert r.status == 'OPTIMAL'
    assert r.schedule.loc[r.schedule.machine_id == 'A', 'start'].iloc[0] >= 4
    assert validate_schedule(f, r.schedule) == []
    bad = r.schedule.copy()
    i = bad.index[bad.machine_id == 'A'][0]
    bad.loc[i, ['start', 'finish']] = [0, 2]
    assert any('outside a continuous available' in x for x in validate_schedule(f, bad))


def test_weighted_tardiness_objective_and_priorities(tiny_factory):
    orders = tiny_factory.orders.copy()
    orders['due_minute'] = 0
    orders.loc[orders.order_id == 'J2', 'priority'] = 5
    f = tiny_factory.replace(orders=orders, routings=tiny_factory.routings.iloc[:1])
    r = solve_schedule(f, objective='weighted_tardiness', time_limit=5, workers=1)
    assert r.status == 'OPTIMAL'
    assert r.schedule.sort_values('start').order_id.tolist() == ['J2', 'J1']
    # J2 completes at 2, J1 at 4: weighted lateness = 5*2 + 1*4 = 14.
    assert r.objective_value == (f.horizon + 1) * 14 + 4


def test_input_validation_and_expansion(tiny_factory):
    routes = tiny_factory.routings.copy(); routes.loc[0, 'minutes_per_unit'] = -1
    with pytest.raises(InputError): tiny_factory.replace(routings=routes)
    with pytest.raises(ValueError): extend_machine_shift(tiny_factory, 'A', 1440)
    m = tiny_factory.machines.copy(); m.loc[m.machine_id == 'A', 'shift_end_minute'] = 20
    f = tiny_factory.replace(machines=m)
    f2, extra = extend_machine_shift(f, 'A', 30)
    assert extra == 10 and available_minutes(f2, 'A') == available_minutes(f, 'A') + 10
    assert f.machines.loc[f.machines.machine_id == 'A', 'shift_end_minute'].iloc[0] == 20


def test_validator_detects_machine_overlap_and_precedence(tiny_factory):
    result = solve_schedule(tiny_factory, time_limit=5, workers=1)
    bad = result.schedule.copy()
    one = bad.index[(bad.order_id == 'J1') & (bad.machine_id == 'A')][0]
    two = bad.index[(bad.order_id == 'J2') & (bad.machine_id == 'A')][0]
    bad.loc[two, ['start', 'finish']] = bad.loc[one, ['start', 'finish']].values
    assert any('overlap' in e for e in validate_schedule(tiny_factory, bad))
    bad = result.schedule.copy()
    successor = bad.index[(bad.order_id == 'J1') & (bad.machine_id == 'B')][0]
    bad.loc[successor, ['start', 'finish']] = [0, 3]
    assert any('precedence violated' in e for e in validate_schedule(tiny_factory, bad))


def test_nonpreemptive_operation_cannot_cross_planned_maintenance(tiny_factory):
    f = tiny_factory.replace(orders=tiny_factory.orders.iloc[:1])
    downtime = pd.DataFrame([['A', 1, 2, 'Maintenance']], columns=['machine_id', 'start_minute', 'end_minute', 'reason'])
    f = f.replace(downtimes=downtime)
    r = solve_schedule(f, time_limit=5, workers=1)
    assert r.status == 'OPTIMAL'
    cut = r.schedule[r.schedule.machine_id == 'A'].iloc[0]
    assert cut.start == 2 and cut.finish == 4
    assert validate_schedule(f, r.schedule) == []
