# Smart Production Planning and Machine Scheduling Optimization System

A runnable operations-research project for a small **synthetic** manufacturing facility. It turns order quantities and product routings into a machine-wise production schedule, then re-optimizes when a machine fails or an urgent order arrives. The core is an optimization engine, not a forecasting or dashboard project.

> **Quick links:** [Mathematical formulation](docs/mathematical_formulation.md) · [Assumptions & CSV schema](docs/assumptions.md) · [Measured sample results](docs/sample_results.md) · [Validation report](docs/test_results.md) · [Portfolio & interview notes](docs/portfolio.md) · [Offline sample Gantt](results/sample_gantt.html)
>
> Working Link:  (https://smartoptimizer.streamlit.app/)

## What works

- **Integer production planning (PuLP/CBC):** choose a quantity for each order using demand, one shared material limit, priority-weighted shortage costs, product costs and aggregate machine-group capacity. Planned quantities can be applied to the scheduler; zero-quantity orders are omitted.
- **Flexible job-shop scheduling (OR-Tools CP-SAT):** select one eligible machine per operation, machine-specific processing time, fixed setup, precedence, release time, non-overlap, recurring shifts, planned maintenance and a finite horizon. Minimize makespan, or minimize weighted tardiness with makespan as a strict tie-breaker.
- **Baselines:** FIFO, earliest due date (EDD) and shortest processing time (SPT) serial schedule-generation rules. A greedy failure is not called a proof of infeasibility.
- **Interactive Plotly Gantt:** view a computed schedule by machine or order, including available idle time, off-shift/unavailable periods, operation details and aborted work. CSV exports are available. `results/sample_gantt.html` is self-contained and works offline.
- **Breakdown rescheduling:** add an outage, show directly affected operations, preserve completed work and unaffected running work, and re-solve. An operation already running on the broken machine is **aborted**, its partial work is recorded as wasted, and the complete setup plus processing restarts on the same machine after repair.
- **Urgent order:** add a new released high-priority order, preserve completed and running operations, and re-solve with an explicit stability/tardiness trade-off. The urgent order bypasses material planning: availability must be checked separately.
- **What-if capacity:** extend one machine's daily shift, re-solve, and optionally estimate a limited cost trade-off using user-supplied rates.
- **Validation:** a separate checker verifies required operations, assignments, durations, releases, precedence, machine conflicts, calendars, downtime and aborted history. The UI rejects an invalid returned schedule.
- **Inputs:** load the bundled factory, edit tables in the app, or upload compatible CSVs. See [the schema](docs/assumptions.md#csv-input-schema).

## Quick start

Requires Python **3.11–3.13**. The dependency range uses PuLP's bundled CBC solver; the tested Linux environment used Python 3.13 and OR-Tools 9.15. For other platforms, verify CBC is available.

```bash
git clone <your-repository-url>
cd smart-production-optimizer
python -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
streamlit run app.py
```

Open the Streamlit URL printed in the terminal (normally `http://localhost:8501`). For a remote container use `streamlit run app.py --server.address 0.0.0.0 --server.port 8501`. This is an unauthenticated local demonstration, not a hardened production deployment.

Run tests:

```bash
pytest -q
# Optional longer end-to-end Streamlit smoke test, including both disruption scenarios:
python scripts/smoke_ui.py
```

Recreate the sample CSVs and regenerate the measured result snapshot:

```bash
python scripts/generate_sample_data.py  # deterministic seed 41; overwrites data/*.csv
python scripts/run_sample.py            # ~40 seconds at the configured limits; overwrites results/ and docs/sample_results.md
```

Time-limited CP-SAT incumbents may differ across runs, CPU speeds and solver versions even with a fixed seed. If CBC cannot be found, install a compatible CBC executable or a PuLP build that includes it. An unknown/failed solver status is never presented as an optimal plan.

## Example workflow

1. **Factory Setup:** use the sample (24 orders, 6 machines, 6 products, 92 required operations), edit tables, or upload all four required CSVs plus optional downtime. Choose the factory-origin date and horizon.
2. **Production Planning:** choose a material limit, solve, inspect shortages and capacity, then click **Use planned quantities for scheduling**. Or skip this page to schedule full demand. The aggregate planner is a relaxation; a subsequent detailed schedule can still be infeasible.
3. **Scheduling:** choose minimum makespan or minimum weighted tardiness, set the solve time, and run CP-SAT. The app also constructs FIFO, EDD and SPT baselines. Read the solver status and bound.
4. **Gantt Chart:** choose any available schedule, filter by machine/order, inspect the tooltips and download the schedule.
5. **Rescheduling:** select an original schedule, a decision minute, and either a breakdown interval or an urgent order. Run the new optimization, inspect the revised and original Gantts, order completion changes, newly late orders, reassignments and machine workload.
6. **Schedule Comparison:** compare returned schedules and optionally extend a shift. Compare like-for-like order scopes; a new urgent order changes the workload. If only `FEASIBLE`, the shown result is an incumbent, not a proven optimum.
7. **Model Configuration:** review enforced constraints, unsupported features, objective expressions and solver status.

All time inputs and schedule rows are integer **minutes from a factory-local midnight origin**. For the sample origin `2026-11-02 00:00`, minute 480 is `2026-11-02 08:00`. Intervals are half-open `[start, finish)`. Makespan is the latest completion measured from the origin and includes calendar gaps; active span is separately available in code. No timezone/DST conversion is performed.

## Example measured results

One 8-second-per-solve sample run produced the following. These are **synthetic-data outcomes**, not a factory deployment or a guarantee of improvement; see [sample results](docs/sample_results.md) for the complete snapshot and disruption/capacity comparisons.

| Method | Status | Cmax, min | Weighted tardiness, min | Late orders |
|---|---|---:|---:|---:|
| FIFO | HEURISTIC | 3,464 | 11,809 | 9 |
| EDD | HEURISTIC | 3,463 | 37 | 2 |
| CP-SAT, makespan | FEASIBLE | 2,446 | 3,389 | 4 |
| CP-SAT, weighted tardiness | FEASIBLE | 2,452 | 0 | 0 |

Those CP-SAT values are feasible incumbents, **not proven optima**. Faster overall completion can trade off against due-date performance. The sample snapshot is regenerated by the script; if regenerated, use `docs/sample_results.md` as the current source of truth rather than this illustrative table.

## Architecture

```text
app.py                        Streamlit interface; no optimization logic here
src/data_loader.py            schema validation and order-to-operation expansion
src/calendars.py              shift, downtime and interval arithmetic
src/production_planning.py    aggregate integer quantity planning
src/scheduling_model.py       CP-SAT flexible job-shop model
src/dispatching_rules.py      FIFO, EDD, SPT baselines
src/schedule_validator.py     independent feasibility checks
src/rescheduling.py           breakdown and urgent-order re-optimization
src/schedule_metrics.py       completion, tardiness and workload comparisons
src/gantt_chart.py            interactive chart from schedule rows
src/capacity_analysis.py      shift-expansion what-if and cost estimate
data/                         reproducible synthetic CSV inputs
results/                      sample schedules, plan and offline HTML Gantt
tests/                        feasibility, optimization, UI and edge-case tests
docs/                         equations, assumptions, sample results, portfolio
scripts/                      data generator, result snapshot and UI smoke test
```

## Boundaries and limitations

Planning uses **optimistic aggregate group capacities** over the whole horizon, using independently minimal eligible unit processing and fixed setup times. It ignores individual due dates, fragmentation and exact assignments. The detailed scheduler is the authority on scheduling feasibility. It does not guarantee that planned demand can be sequenced.

The model does **not** implement sequence-dependent setups, operators/tools, split batches, partial-operation credit, inventory balance, time-phased material arrivals, overtime or stochastic failures. One same-day recurring shift per machine is modeled; arbitrary shift patterns and cross-midnight shifts are not directly represented. The model is deterministic and minute-granular. Only one disruption is applied at a time to a selected original schedule; chained revisions with aborted histories are not supported in the UI. The sample costs and raw-material units are illustrative. There is no automatic persistent database or authentication; use the CSV downloads to save user-generated plans and schedules. See [assumptions](docs/assumptions.md).

## License

Project code is provided under the [MIT License](LICENSE). Third-party packages and the embedded Plotly JavaScript in the generated offline chart retain their own licenses.
