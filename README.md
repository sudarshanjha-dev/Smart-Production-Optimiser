# Smart Production Planning and Machine Scheduling Optimization System

An operations-research application with two explicitly separated workspaces:

- **Real textile case study (default):** reconstruct and optimize the MIT-licensed, three-machine Zenodo textile input using OR-Tools CP-SAT, with independent validation and a reproducible baseline.
- **Synthetic factory:** the original quantity planning, flexible scheduling, Gantt and disruption reoptimization workflows remain available. Its illustrative orders, breakdowns and urgent orders are not presented as real events.

Both produce computed decision-support schedules; neither is a claim of factory deployment or historical execution.

> **Quick links:** [Mathematical formulation](docs/mathematical_formulation.md) · [Assumptions & CSV schema](docs/assumptions.md) · [Measured sample results](docs/sample_results.md) · [Validation report](docs/test_results.md) · [Portfolio & interview notes](docs/portfolio.md) · [Offline synthetic Gantt](results/sample_gantt.html) · [Textile dataset/schema](docs/textile_dataset.md) · [Textile model and actual results](docs/textile_model_and_results.md)
>
> Existing upstream app: https://smartoptimizer.streamlit.app/ — the changes in this archive have **not** been pushed or deployed there.

## Real textile workspace

Choose **Real textile case study** (the default) in the sidebar. The bundled [Zenodo record 4106746](https://doi.org/10.5281/zenodo.4106746) input is MIT-licensed, attributed in `data/textile/ATTRIBUTION.txt`, and works offline. The adapter verifies and validates it; an optional remote refresh is cached and checksum-verified. A compatible upload is identified separately. The 15 source requests expand to 132 product units and 275 task runs across three machines. The app displays source requests, all task modes and compatibility, warnings, controls, solver status and bounds, an actual returned Gantt/table, CSVs, KPIs and an independently validated equal-constraint baseline comparison.

Available objectives are (1) minimize makespan or (2) minimize total selected raw mode-profile values subject to a user-chosen hard makespan cap. The second is an energy **proxy**, not time-dependent grid-cost optimization. Both respect eligible mode/machine pairs, non-overlap on machines, five-minute durations, source time-leap boundaries, source deadline, explicit order and cross-task collision. No artificial product-array routing is assumed.

**Important choices:** JSON field names and the paper disagree about the order direction; the UI exposes both. Per-unit order scope is an assumption. The default conservative unit policy forbids concurrent tasks for one product unit; an alternate permits independent tasks to overlap, as suggested by rows sharing product identifiers in the published statistics workbook. Machine and collision restrictions always remain. Energy values have a PV/unit inconsistency, so the source-style score is not verified currency or kWh. The published output is a reference, **not** the benchmark or a proven optimum. [All fields, limitations and audit](docs/textile_dataset.md) · [equations and measured benchmark](docs/textile_model_and_results.md).

### Measured real-data snapshot

With JSON order, conservative unit policy, 8 seconds, one worker and seed 0, the validated deadline-first FIFO baseline completed in **1,016 working slots**, versus a **FEASIBLE** CP-SAT incumbent of **834 slots** (17.91% lower; lower bound 587). The 834-slot incumbent matched the load-balanced warm-start in this run. The source-style score rose from **48.5770** to **58.4643**; it is not verified money or energy savings. Under a 1,016-slot cap, the separate profile objective returned **1,320,574** raw units versus FIFO's **1,330,241** (0.73% lower), also FEASIBLE. Details and CSVs are in `results/textile/` and `results/textile_profile/`; time-limited runs can differ.

## What works in the original synthetic workspace

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
# If using the supplied clean ZIP, extract it and cd into Smart-Production-Optimiser.
# Alternatively, start from the pinned upstream commit and apply the supplied patch:
git clone --filter=blob:none --sparse https://github.com/sudarshanjha-dev/Smart-Production-Optimiser.git
cd Smart-Production-Optimiser
git sparse-checkout set --no-cone '/*' '!/my_new_env/'
git checkout 4ae045cd125f583d0f3d81c7758b2c0187e91d44
git apply --check /absolute/path/to/Smart-Production-Optimiser-textile.patch
git apply /absolute/path/to/Smart-Production-Optimiser-textile.patch
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

Recreate the textile benchmark and (optionally) audit the published output and workbook:

```bash
python scripts/benchmark_textile.py --seconds 8 --workers 1 --direction json
python scripts/benchmark_textile.py --seconds 8 --workers 1 --direction json --objective profile --makespan-limit 1016 --output-dir results/textile_profile
python scripts/audit_textile_reference.py  # optional network download; temporary files
```

Recreate the **synthetic** sample CSVs and regenerate its separate measured result snapshot:

```bash
python scripts/generate_sample_data.py  # deterministic seed 41; overwrites data/*.csv
python scripts/run_sample.py            # ~40 seconds at the configured limits; overwrites results/ and docs/sample_results.md
```

Time-limited CP-SAT incumbents may differ across runs, CPU speeds and solver versions even with a fixed seed. If CBC cannot be found, install a compatible CBC executable or a PuLP build that includes it. An unknown/failed solver status is never presented as an optimal plan.

## Example workflow

For the textile data, leave the sidebar on **Real textile case study**, choose the order direction and unit policy, set an objective and solver limit, and click **Run textile optimization**. Read status, validation and any cost trade-off; inspect the actual Gantt/table and download CSVs. For the original workflow, switch **Dataset → Synthetic factory**:

1. **Factory Setup:** use the sample (24 orders, 6 machines, 6 products, 92 required operations), edit tables, or upload all four required CSVs plus optional downtime. Choose the factory-origin date and horizon.
2. **Production Planning:** choose a material limit, solve, inspect shortages and capacity, then click **Use planned quantities for scheduling**. Or skip this page to schedule full demand. The aggregate planner is a relaxation; a subsequent detailed schedule can still be infeasible.
3. **Scheduling:** choose minimum makespan or minimum weighted tardiness, set the solve time, and run CP-SAT. The app also constructs FIFO, EDD and SPT baselines. Read the solver status and bound.
4. **Gantt Chart:** choose any available schedule, filter by machine/order, inspect the tooltips and download the schedule.
5. **Rescheduling:** select an original schedule, a decision minute, and either a breakdown interval or an urgent order. Run the new optimization, inspect the revised and original Gantts, order completion changes, newly late orders, reassignments and machine workload.
6. **Schedule Comparison:** compare returned schedules and optionally extend a shift. Compare like-for-like order scopes; a new urgent order changes the workload. If only `FEASIBLE`, the shown result is an incumbent, not a proven optimum.
7. **Model Configuration:** review enforced constraints, unsupported features, objective expressions and solver status.

In the synthetic workspace, time inputs and schedule rows are integer **minutes from a factory-local midnight origin**. For the sample origin `2026-11-02 00:00`, minute 480 is `2026-11-02 08:00`. Intervals are half-open `[start, finish)`. Makespan is the latest completion measured from the origin and includes calendar gaps; active span is separately available in code. No timezone/DST conversion is performed.

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
src/textile_data.py           strict Zenodo adapter, provenance and request expansion
src/textile_scheduling.py     textile CP-SAT choices, constraints and objectives
src/textile_dispatching.py    equal-constraint baseline and warm-start heuristics
src/textile_validation.py     independent textile schedule validator
src/textile_metrics.py        raw score, workload and fair comparisons
src/textile_gantt.py          calendar-aware Plotly schedule
src/textile_ui.py             separate real-textile Streamlit workspace
data/textile/                 pinned MIT-licensed source input and attribution
data/                         reproducible synthetic CSV inputs
results/                      sample schedules, plan and offline HTML Gantt
tests/                        feasibility, optimization, UI and edge-case tests
docs/                         equations, assumptions, sample results, portfolio
scripts/                      data generator, result snapshot and UI smoke test
```

## Boundaries and limitations

The textile model has its own limitations documented [here](docs/textile_model_and_results.md#boundaries); particularly, it does not optimize time-varying grid score or simulate textile-specific disruptions.

The original **synthetic** planning model uses **optimistic aggregate group capacities** over the whole horizon, using independently minimal eligible unit processing and fixed setup times. It ignores individual due dates, fragmentation and exact assignments. The detailed scheduler is the authority on scheduling feasibility. It does not guarantee that planned demand can be sequenced.

The model does **not** implement sequence-dependent setups, operators/tools, split batches, partial-operation credit, inventory balance, time-phased material arrivals, overtime or stochastic failures. One same-day recurring shift per machine is modeled; arbitrary shift patterns and cross-midnight shifts are not directly represented. The model is deterministic and minute-granular. Only one disruption is applied at a time to a selected original schedule; chained revisions with aborted histories are not supported in the UI. The sample costs and raw-material units are illustrative. There is no automatic persistent database or authentication; use the CSV downloads to save user-generated plans and schedules. See [assumptions](docs/assumptions.md).

## License

Project code is provided under the [MIT License](LICENSE). The Zenodo input is separately attributed and MIT-licensed; see `data/textile/ATTRIBUTION.txt`. Third-party packages and the embedded Plotly JavaScript in the generated offline chart retain their own licenses.

## Deploy your copy (not performed here)

The upstream repository already tracks a large `my_new_env/`; the clean ZIP and this patch do not include it. `.gitignore` does not remove files already tracked in upstream history. Use the sparse-checkout/patch instructions above, review the changes, and push only to a repository or fork you control. For Streamlit Community Cloud, select that repository and branch, set the main file to `app.py`, and deploy using `requirements.txt`. The bundled textile data requires no secrets or external API. The existing public deployment will remain unchanged until its owner deploys the modified branch. The app is an unauthenticated demonstration, not a hardened production service.

After applying the patch to a checkout whose `origin` is your own writable fork, an example branch/push sequence is:

```bash
git switch -c textile-integration
git add .gitattributes .gitignore README.md app.py data/textile docs/textile_dataset.md docs/textile_model_and_results.md docs/test_results.md \
  results/textile results/textile_profile scripts/audit_textile_reference.py scripts/benchmark_textile.py scripts/smoke_ui.py \
  src/textile_data.py src/textile_dispatching.py src/textile_gantt.py src/textile_metrics.py src/textile_scheduling.py src/textile_ui.py src/textile_validation.py \
  tests/conftest.py tests/test_streamlit_app.py tests/test_textile_artifacts.py tests/test_textile_data.py tests/test_textile_schedule.py tests/test_textile_streamlit_app.py
git diff --cached --stat
git commit -m "Integrate Zenodo textile scheduling"
git push -u origin textile-integration
```

For a self-hosted demo, the exact server command is:

```bash
streamlit run app.py --server.address 0.0.0.0 --server.port 8501 --server.headless true
```
