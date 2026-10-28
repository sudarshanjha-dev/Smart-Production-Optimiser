"""Solve and export a transparent snapshot of synthetic sample results.

Run from the repository root: python scripts/run_sample.py
Time-limited solver results can differ by machine / OR-Tools version.
"""
from pathlib import Path
import sys
from datetime import timedelta
from importlib.metadata import version
import platform
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.capacity_analysis import cost_estimate, extend_machine_shift
from src.data_loader import load_sample
from src.dispatching_rules import dispatch_schedule
from src.gantt_chart import make_gantt
from src.production_planning import plan_production
from src.rescheduling import reschedule_breakdown, reschedule_urgent_order
from src.schedule_metrics import compare_schedules, summary_metrics
from src.schedule_validator import validate_schedule
from src.scheduling_model import solve_schedule


def table(headers, rows):
    fmt = lambda row: '| ' + ' | '.join(str(x) for x in row) + ' |'
    return '\n'.join([fmt(headers), fmt(['---'] * len(headers))] + [fmt(row) for row in rows])


def main():
    f = load_sample()
    out = ROOT / 'results'; out.mkdir(exist_ok=True)
    # Avoid leaving a previous run's schedule behind if this run has no incumbent.
    generated = ['fifo.csv', 'edd.csv', 'spt.csv', 'cp_sat_makespan.csv', 'cp_sat_weighted_tardiness.csv',
                 'breakdown_schedule.csv', 'breakdown_aborted_history.csv', 'urgent_order_schedule.csv',
                 'capacity_expansion_schedule.csv', 'quantity_plan_85pct_material.csv', 'sample_gantt.html']
    for name in generated:
        (out / name).unlink(missing_ok=True)
    snapshots = {}
    for rule in ('FIFO', 'EDD', 'SPT'):
        snapshots[rule] = dispatch_schedule(f, rule)
    for obj in ('makespan', 'weighted_tardiness'):
        print(f'Solving {obj} for up to 8 seconds…', flush=True)
        snapshots[f'CP-SAT {obj}'] = solve_schedule(f, obj, time_limit=8, workers=1)
    summaries = []
    for label, result in snapshots.items():
        if not result.has_schedule:
            summaries.append([label, result.status, '—', '—', '—', '—', '—'])
            continue
        assert not validate_schedule(f, result.schedule), label
        result.schedule.to_csv(out / (label.replace(' ', '_').replace('-', '_').lower() + '.csv'), index=False)
        m = summary_metrics(f, result.schedule)
        bound = f'{result.best_bound:,.0f}' if result.best_bound is not None else '—'
        summaries.append([label, result.status, m['makespan'], m['total_tardiness'], m['weighted_tardiness'], m['late_orders'], bound])
    # Fixed, manually inspectable disruption on the deterministic EDD schedule.
    base = snapshots['EDD'].schedule
    now = 700
    print('Solving breakdown scenario…', flush=True)
    broken_factory, broken = reschedule_breakdown(f, base, 'M01', now, 880, time_limit=8, workers=1)
    print('Solving urgent order scenario…', flush=True)
    urgent_factory, urgent = reschedule_urgent_order(f, base, now=now, order_id='URG-001', product_id='P-A', quantity=8,
                                                      due=1600, priority=5, time_limit=8, workers=1)
    scenario_rows = []
    for label, revised_factory, result in [('Breakdown', broken_factory, broken), ('Urgent order', urgent_factory, urgent)]:
        if result.has_schedule:
            assert not validate_schedule(revised_factory, result.schedule, result.history)
            result.schedule.to_csv(out / (label.lower().replace(' ', '_') + '_schedule.csv'), index=False)
            if not result.history.empty:
                result.history.to_csv(out / 'breakdown_aborted_history.csv', index=False)
            cmp = compare_schedules(f, base, revised_factory, result.schedule, result.history)
            scenario_rows.append([label, result.status, cmp['original']['makespan'], cmp['revised']['makespan'],
                                  cmp['original']['weighted_tardiness'], cmp['revised']['weighted_tardiness'],
                                  cmp['newly_late_orders'], cmp['machine_reassignments'], cmp['revised']['aborted_busy_minutes']])
        else:
            scenario_rows.append([label, result.status, '—', '—', '—', '—', '—', '—', '—'])
    stock = int(sum(o.quantity * f.products.set_index('product_id').loc[o.product_id, 'material_per_unit'] for o in f.orders.itertuples(index=False)) * .85)
    plan = plan_production(f, stock)
    if plan.has_plan:
        plan.order_plan.to_csv(out / 'quantity_plan_85pct_material.csv', index=False)
    # Make a fully self-contained, offline-interactive sample Gantt.
    chart_result = snapshots['CP-SAT makespan'] if snapshots['CP-SAT makespan'].has_schedule else snapshots['EDD']
    make_gantt(f, chart_result.schedule).write_html(out / 'sample_gantt.html', include_plotlyjs=True, full_html=True)
    print('Solving shift-extension what-if…', flush=True)
    expanded, extra = extend_machine_shift(f, 'M06', 1080)
    expansion = solve_schedule(expanded, 'weighted_tardiness', time_limit=8, workers=1)
    capacity_text = f"Status: **{expansion.status}**."
    if expansion.has_schedule and snapshots['CP-SAT weighted_tardiness'].has_schedule:
        assert not validate_schedule(expanded, expansion.schedule)
        expansion.schedule.to_csv(out / 'capacity_expansion_schedule.csv', index=False)
        estimate = cost_estimate(f, snapshots['CP-SAT weighted_tardiness'].schedule, expanded, expansion.schedule, extra, 12, 1)
        capacity_text += (f" M06's shift is extended from 17:00 to 18:00, adding {extra} available minutes over the horizon. "
                          f"Weighted tardiness changed from {estimate['original_weighted_tardiness']} to {estimate['expanded_weighted_tardiness']}; "
                          f"makespan changed from {estimate['original_makespan']} to {estimate['expanded_makespan']} minutes. "
                          f"At hypothetical rates of 12 cost units per added available hour and 1 cost unit per weighted tardy minute, "
                          f"the estimated net is {estimate['estimated_net_value']:.2f} cost units "
                          f"(capacity cost {estimate['estimated_extra_capacity_cost']:.2f}; delay-cost saving {estimate['estimated_delay_cost_saving']:.2f}).")
    planning_text = (f"Status **{plan.status}**; available material {stock} units, used {plan.material_used}; "
                     f"demand {int(plan.order_plan.demand_quantity.sum())} units, planned {int(plan.order_plan.planned_quantity.sum())}, "
                     f"unmet {int(plan.order_plan.shortage_quantity.sum())}; objective {plan.objective_value:.2f} cost units. "
                     "This is an aggregate plan, not a scheduling-feasibility proof.") if plan.has_plan else f'Planning status: {plan.status}.'
    versions = f"Python {platform.python_version()}, OR-Tools {version('ortools')}, PuLP {version('pulp')}, Pandas {version('pandas')}"
    document = f'''# Sample results — synthetic factory

These are **measured outputs of one local run**, not claims about a real factory. Data are generated with seed 41. Environment: {versions}. The CP-SAT runs below used one worker, seed 41, and an 8-second limit per solve; wall-clock-limited incumbents and bounds can vary by computer, dependency version and run. Reproduce with `python scripts/run_sample.py`. All returned schedules were checked by the independent validator.

Factory origin: {f.origin:%Y-%m-%d %H:%M} local; horizon: {f.horizon} minutes; {len(f.orders)} orders, {len(f.machines)} machines, {len(f.products)} products. Cmax is minutes from the origin, including nonworking time. Tardiness is also in minutes. Weighted tardiness is Σ(priority × tardiness).

## Dispatch rules and optimizer

{table(['Method', 'Status', 'Cmax', 'Total tardiness', 'Weighted tardiness', 'Late orders', 'Best objective bound'], summaries)}

A **FEASIBLE** result is not proven optimal; dispatch rules are heuristics. The best bound belongs to the solver's raw selected objective, not always to Cmax alone. For weighted tardiness the raw objective is `(H+1) × weighted tardiness + Cmax`. Comparison does not imply every metric improves.

## Dynamic rescheduling

Both scenarios start from the **same EDD schedule**. At minute 700 ({f.origin + timedelta(minutes=700):%Y-%m-%d %H:%M}), M01 breaks down through minute 880. The operation running on M01 is aborted and restarted in full on M01 after repair; other running and completed operations are fixed. The separate urgent scenario inserts `URG-001` (P-A, quantity 8, priority 5, release 700, due 1600); material availability for it is assumed, not planned. Both use the documented stability objective, not the baseline EDD rule.

{table(['Scenario', 'Status', 'Original Cmax', 'Revised Cmax', 'Original weighted tardiness', 'Revised weighted tardiness', 'Newly late existing orders', 'Machine changes', 'Aborted min'], scenario_rows)}

The urgent scenario contains an additional order and therefore its total tardiness is not a like-for-like comparison of the original 24 orders. Newly late counts only original orders that were on time before and late afterward.

## Aggregate production planning

{planning_text}

## Capacity what-if

{capacity_text}

The cost rates are illustrative, not observed savings. The comparison uses the two returned weighted-tardiness incumbents; if either is only FEASIBLE, it does not prove the best achievable benefit of the extension. Cost is charged on all additional available hours over the horizon, not just used hours, and excludes other financial effects.

## Files

`results/` contains the exported schedules, plan, interrupted-history CSV where applicable, and `sample_gantt.html`, an offline interactive chart generated from the selected sample schedule. Solver results may differ from this snapshot when regenerated.
'''
    (ROOT / 'docs' / 'sample_results.md').write_text(document, encoding='utf-8')
    print('\n' + document)

if __name__ == '__main__':
    main()
