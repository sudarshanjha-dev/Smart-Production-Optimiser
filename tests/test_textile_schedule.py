import copy
import json
import pytest
from src.textile_data import TextileInputError, parse_textile_json, load_published_bytes
from src.textile_dispatching import dispatch_textile
from src.textile_scheduling import solve_textile
from src.textile_metrics import textile_metrics, textile_machine_metrics, compare_textile
from src.textile_validation import validate_textile_schedule


def make_problem(raw, rule='json'):
    return parse_textile_json(json.dumps(raw), rule)


def test_exact_small_makespan_and_profile_objective(textile_fixture):
    p = make_problem(textile_fixture)
    baseline = dispatch_textile(p)
    result = solve_textile(p, time_limit=3, workers=1, baseline=baseline)
    assert result.status == 'OPTIMAL'
    assert result.objective_value == result.best_bound == 4
    assert validate_textile_schedule(p, result.schedule) == []
    energy = solve_textile(p, time_limit=3, workers=1, baseline=baseline,
                           objective='profile', makespan_limit=4)
    assert energy.status == 'OPTIMAL'
    assert energy.objective == 'total_mode_profile_raw'
    assert energy.objective_value == energy.best_bound == 28  # 10+10+4+4
    assert validate_textile_schedule(p, energy.schedule, makespan_limit=4) == []
    too_short = solve_textile(p, time_limit=3, workers=1, baseline=baseline,
                               objective='profile', makespan_limit=3)
    assert too_short.status == 'INFEASIBLE' and not too_short.has_schedule


def test_solve_both_order_directions(textile_fixture):
    for direction, first, second in [('json','X','Y'), ('paper','Y','X')]:
        p = make_problem(textile_fixture, direction)
        result = solve_textile(p, time_limit=3, workers=1)
        assert result.status == 'OPTIMAL'
        s = result.schedule.set_index('task')
        assert s.loc[first].end_slot <= s.loc[second].start_slot
        assert not validate_textile_schedule(p, result.schedule)


def test_hard_source_deadline_is_not_a_soft_tardiness(textile_fixture):
    bad = copy.deepcopy(textile_fixture)
    bad['product_requests'][0]['deadline'] = 3
    p = make_problem(bad)
    assert dispatch_textile(p).status == 'HEURISTIC_FAILED'
    result = solve_textile(p, time_limit=3, workers=1)
    assert result.status == 'INFEASIBLE' and not result.has_schedule


def test_validator_finds_incompatible_mode_deadline_duration_and_leap(textile_fixture):
    p = make_problem(textile_fixture)
    schedule = dispatch_textile(p).schedule
    x = schedule.index[schedule.task == 'X'][0]
    invalid = schedule.copy(); invalid.loc[x, 'machine_id'] = 'M2'
    assert any('incompatible' in e for e in validate_textile_schedule(p, invalid))
    invalid = schedule.copy(); invalid.loc[x, 'end_slot'] = 3
    assert any('duration' in e for e in validate_textile_schedule(p, invalid))
    invalid = schedule.copy(); invalid.loc[x, ['start_slot','end_slot']] = [4,6]
    assert any('time leap' in e for e in validate_textile_schedule(p, invalid))
    invalid = schedule.copy(); invalid.loc[x, ['start_slot','end_slot']] = [7,9]
    assert any('deadline violated' in e for e in validate_textile_schedule(p, invalid))
    assert any('makespan cap' in e for e in validate_textile_schedule(p, schedule, makespan_limit=3))
    invalid = schedule.iloc[:-1].copy()
    assert any('Missing task run' in e for e in validate_textile_schedule(p, invalid))


def test_validator_catches_machine_and_unit_overlap_and_order(textile_fixture):
    p = make_problem(textile_fixture)
    schedule = dispatch_textile(p).schedule
    x, y = (schedule.index[schedule.task == t][0] for t in ('X','Y'))
    invalid = schedule.copy(); invalid.loc[y, ['start_slot','end_slot']] = [0,2]
    issues = validate_textile_schedule(p, invalid)
    assert any('Product unit' in e and 'overlap' in e for e in issues)
    assert any('task-order' in e for e in issues)
    assert any('Collision' in e for e in issues)
    raw = copy.deepcopy(textile_fixture)
    raw['products'] = [{'id':'P', 'tasks':[{'task':'X','runs':1}]}]
    raw['product_requests'] = [{'product':'P','amount':2}]
    raw['constraints'] = []
    p2 = make_problem(raw); sched = dispatch_textile(p2).schedule
    idx = sched.index[1]
    sched.loc[idx, ['start_slot','end_slot']] = [0,2]
    assert any('Machine M1' in e and 'overlap' in e for e in validate_textile_schedule(p2, sched))


def test_collision_across_distinct_units_and_same_type_overlap_allowed(textile_fixture):
    raw = copy.deepcopy(textile_fixture)
    raw['products'] = [{'id':'P', 'tasks':[{'task':'X','runs':1}]},
                       {'id':'Q', 'tasks':[{'task':'Y','runs':1}]}]
    raw['product_requests'] = [{'product':'P','amount':1}, {'product':'Q','amount':1}]
    raw['constraints'] = [raw['constraints'][1]]
    p = make_problem(raw); r = solve_textile(p, time_limit=3, workers=1)
    assert r.status == 'OPTIMAL' and r.objective_value == 4
    invalid = r.schedule.copy()
    iy = invalid.index[invalid.task == 'Y'][0]
    invalid.loc[iy, ['start_slot','end_slot']] = [0,2]
    assert any('Collision' in e for e in validate_textile_schedule(p, invalid))
    # A collision X/Y must not serialize two X tasks on different machines.
    raw['machines'][1]['task_modes'].append('X1')
    raw['product_requests'] = [{'product':'P','amount':2}]
    p = make_problem(raw); r = solve_textile(p, time_limit=3, workers=1)
    assert r.status == 'OPTIMAL' and r.objective_value == 2


def test_metrics_are_recomputed_and_comparison_requires_feasible_schedule(textile_fixture):
    p = make_problem(textile_fixture); baseline = dispatch_textile(p)
    m = textile_metrics(p, baseline.schedule)
    assert (m['makespan_slots'],m['makespan_working_minutes']) == (4,20)
    assert m['total_profile_raw'] == 28
    assert m['grid_draw_raw'] == 28 and m['source_style_cost_score'] == 14
    assert m['mean_machine_utilization_pct'] == 50
    assert all(textile_machine_metrics(p, baseline.schedule).utilization_pct == 50)
    comparison = compare_textile(p, baseline.schedule, baseline.schedule)
    assert comparison.loc[comparison.metric == 'Makespan (working slots)', 'reduction_pct'].iloc[0] == 0
    bad = baseline.schedule.copy(); bad.loc[bad.index[0], 'machine_id'] = 'fake'
    with pytest.raises(ValueError, match='invalid schedule'):
        compare_textile(p, baseline.schedule, bad)


def test_published_case_solver_returns_a_valid_result_or_truthful_status():
    blob, _ = load_published_bytes(); p = parse_textile_json(blob)
    baseline = dispatch_textile(p)
    r = solve_textile(p, time_limit=2, workers=1, baseline=baseline)
    assert r.status in {'FEASIBLE','OPTIMAL','UNKNOWN'}
    if r.has_schedule:
        assert not validate_textile_schedule(p, r.schedule)
        assert r.metadata['warm_start_source']
        assert textile_metrics(p, r.schedule)['deadline_units_on_time'] == 1


def test_multiobjective_profile_tradeoff_is_real(textile_fixture):
    raw = copy.deepcopy(textile_fixture)
    raw['task_modes'] = [{'id':'fast', 'power':[10]}, {'id':'efficient', 'power':[1,1]}]
    raw['tasks'] = [{'id':'X', 'task_modes':['fast','efficient']}]
    raw['machines'] = [{'id':'M1','task_modes':['fast']}, {'id':'M2','task_modes':['efficient']}]
    raw['products'] = [{'id':'P','tasks':[{'task':'X','runs':1}]}]
    raw['constraints'] = []
    p = make_problem(raw)
    fast = solve_textile(p, time_limit=2, workers=1)
    efficient = solve_textile(p, time_limit=2, workers=1, objective='profile', makespan_limit=2)
    constrained = solve_textile(p, time_limit=2, workers=1, objective='profile', makespan_limit=1)
    assert fast.status == 'OPTIMAL' and fast.objective_value == 1 and fast.schedule.mode_id.iloc[0] == 'fast'
    assert efficient.status == 'OPTIMAL' and efficient.objective_value == 2 and efficient.schedule.mode_id.iloc[0] == 'efficient'
    assert constrained.status == 'OPTIMAL' and constrained.objective_value == 10 and constrained.schedule.mode_id.iloc[0] == 'fast'


def test_repeated_runs_are_individually_assigned_and_ordered(textile_fixture):
    raw = copy.deepcopy(textile_fixture)
    raw['products'][0]['tasks'][0]['runs'] = 2
    raw['product_requests'][0]['deadline'] = 10
    p = make_problem(raw); r = solve_textile(p, time_limit=3, workers=1)
    assert r.status == 'OPTIMAL' and len(r.schedule) == 3
    x = r.schedule[r.schedule.task == 'X'].sort_values('run_index')
    y = r.schedule[r.schedule.task == 'Y'].iloc[0]
    assert x.iloc[0].end_slot <= x.iloc[1].start_slot and x.iloc[1].end_slot <= y.start_slot
    assert not validate_textile_schedule(p, r.schedule)


def test_uploaded_cycles_and_extra_fields_are_rejected(textile_fixture):
    raw = copy.deepcopy(textile_fixture)
    raw['constraints'].append({'type':'Order','parameter':{'first_task':'Y','second_task':'X'}})
    with pytest.raises(TextileInputError, match='cyclic'):
        make_problem(raw)
    raw = copy.deepcopy(textile_fixture); raw['products'][0]['setup_time'] = 2
    with pytest.raises(TextileInputError, match='unsupported fields'):
        make_problem(raw)


def test_same_unit_exclusivity_is_a_selectable_assumption(textile_fixture):
    raw = copy.deepcopy(textile_fixture)
    raw['constraints'] = []  # Independent requirements; no source order/collision.
    encoded = json.dumps(raw)
    conservative = parse_textile_json(encoded, unit_exclusive=True)
    permissive = parse_textile_json(encoded, unit_exclusive=False)
    strict = solve_textile(conservative, time_limit=3, workers=1)
    parallel = solve_textile(permissive, time_limit=3, workers=1)
    assert strict.status == parallel.status == 'OPTIMAL'
    assert strict.objective_value == 4 and parallel.objective_value == 2
    assert not validate_textile_schedule(permissive, parallel.schedule)
    assert any('Product unit' in e and 'overlap' in e for e in validate_textile_schedule(conservative, parallel.schedule))


def test_repeated_runs_can_overlap_when_unit_policy_allows(textile_fixture):
    raw = copy.deepcopy(textile_fixture)
    raw['machines'][1]['task_modes'].append('X1')
    raw['products'] = [{'id':'P', 'tasks':[{'task':'X','runs':2}]}]
    raw['constraints'] = []
    p = parse_textile_json(json.dumps(raw), unit_exclusive=False)
    baseline = dispatch_textile(p)
    optimized = solve_textile(p, time_limit=3, workers=1)
    assert baseline.schedule.end_slot.max() == 2
    assert optimized.status == 'OPTIMAL' and optimized.objective_value == 2
    assert not validate_textile_schedule(p, baseline.schedule)
    assert not validate_textile_schedule(p, optimized.schedule)
