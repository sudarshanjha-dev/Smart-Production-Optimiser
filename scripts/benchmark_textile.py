"""Export a measured equal-constraint textile baseline and CP-SAT schedule.

Examples from repository root:
  python scripts/benchmark_textile.py --seconds 8 --workers 1 --direction json
  python scripts/benchmark_textile.py --seconds 8 --objective profile --makespan-limit 1016
Wall-clock limits can yield different incumbents on different machines/versions.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
import json
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.textile_data import load_published_bytes, parse_textile_json
from src.textile_dispatching import dispatch_textile
from src.textile_metrics import compare_textile, textile_metrics
from src.textile_scheduling import solve_textile
from src.textile_validation import validate_textile_schedule


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seconds', type=float, default=8.0)
    parser.add_argument('--workers', type=int, default=1)
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--direction', choices=('json','paper'), default='json')
    parser.add_argument('--allow-unit-overlap', action='store_true')
    parser.add_argument('--objective', choices=('makespan','profile'), default='makespan')
    parser.add_argument('--makespan-limit', type=int)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'results' / 'textile')
    args = parser.parse_args()
    blob, provenance = load_published_bytes()
    instance = parse_textile_json(blob, args.direction, unit_exclusive=not args.allow_unit_overlap)
    baseline = dispatch_textile(instance)
    result = solve_textile(instance, time_limit=args.seconds, workers=args.workers, seed=args.seed,
                           baseline=baseline, objective=args.objective, makespan_limit=args.makespan_limit)
    cap = args.makespan_limit if args.objective == 'profile' else None
    baseline_errors = validate_textile_schedule(instance, baseline.schedule, makespan_limit=cap) if baseline.has_schedule else [baseline.message]
    result_errors = validate_textile_schedule(instance, result.schedule, makespan_limit=cap) if result.has_schedule else [result.message]
    record = {'generated_utc':datetime.now(timezone.utc).isoformat(), 'python':platform.python_version(),
              'ortools':version('ortools'), 'platform':platform.platform(), 'input_provenance':provenance,
              'input_sha256':instance.input_hash, 'order_interpretation':args.direction,
              'unit_exclusive':instance.unit_exclusive, 'time_limit_seconds':args.seconds,
              'workers':args.workers, 'seed':args.seed, 'objective':args.objective,
              'makespan_limit':cap, 'baseline_rule':'deadline-first FIFO; earliest-finish eligible machine/mode',
              'baseline':{'status':baseline.status, 'validation_errors':baseline_errors},
              'solver':{'status':result.status, 'objective_value':result.objective_value, 'best_bound':result.best_bound,
                        'elapsed_seconds_including_build':result.solve_seconds, 'metadata':result.metadata,
                        'validation_errors':result_errors}}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    # Avoid stale artifacts being mistaken for the current run when a solver
    # returns UNKNOWN or a baseline violates a newly selected cap.
    for name in ('baseline.csv', 'optimized.csv', 'comparison.csv', 'benchmark.json'):
        (args.output_dir / name).unlink(missing_ok=True)
    if baseline.has_schedule:
        baseline.schedule.assign(order_interpretation=args.direction, unit_exclusive=instance.unit_exclusive,
                                 input_sha256=instance.input_hash).to_csv(args.output_dir / 'baseline.csv', index=False)
        record['baseline']['metrics'] = textile_metrics(instance, baseline.schedule)
    if result.has_schedule:
        result.schedule.assign(order_interpretation=args.direction, unit_exclusive=instance.unit_exclusive,
                               input_sha256=instance.input_hash).to_csv(args.output_dir / 'optimized.csv', index=False)
        record['solver']['metrics'] = textile_metrics(instance, result.schedule)
    if baseline.has_schedule and result.has_schedule and not baseline_errors and not result_errors:
        comparison = compare_textile(instance, baseline.schedule, result.schedule)
        comparison.to_csv(args.output_dir / 'comparison.csv', index=False)
        record['comparison_valid_under_same_constraints'] = True
        record['makespan_reduction_pct'] = float(comparison.loc[comparison.metric == 'Makespan (working slots)', 'reduction_pct'].iloc[0])
        print(comparison.to_string(index=False))
    else:
        record['comparison_valid_under_same_constraints'] = False
        print('No equal-constraint comparison: one result is missing or the baseline violates the selected cap.')
    (args.output_dir / 'benchmark.json').write_text(json.dumps(record, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print('\nBaseline:', baseline.status, '| CP-SAT:', result.status, '| Objective:', result.objective_value,
          '| Best bound:', result.best_bound, '| Files:', args.output_dir)

if __name__ == '__main__': main()
