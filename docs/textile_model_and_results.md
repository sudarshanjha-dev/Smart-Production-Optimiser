# Textile model and measured results

## Mathematical formulation

For each required run `i`, expand `amount × runs` from the validated input. Its compatible choices `A_i` consist of machine `m` and source task mode `k`. A Boolean `x_i,m,k` selects exactly one choice, and integers `s_i`, `e_i` are start/end working-slot boundaries. Optional machine intervals enforce `e_i = s_i + d_k` when selected, with `d_k = len(power_k)`. Each interval lies within one of the source working windows `[0,192]`, `[192,384]`, …, `[960,1152]` for the published file. Thus starts and ends can touch a leap but cannot cross it. This uses one-minute naming nowhere: **one slot is five minutes**.

- **Assignment:** `sum_(m,k in A_i) x_i,m,k = 1`; only mode/machine pairs present in both task and machine lists are eligible.
- **Machine exclusivity:** selected intervals on the same machine satisfy `NoOverlap`.
- **Product-unit policy:** in the default conservative policy, all intervals for a unit satisfy `NoOverlap`. The alternate policy omits this extra resource constraint while keeping all other constraints.
- **Explicit per-unit order:** for a unit having both constrained task types, every run of selected first task ends before every run of selected second task starts. The JSON-name or paper direction is selected explicitly. Repeated runs of the same type have ordered **starts** only, to break label symmetry; no artificial end-before-start constraint is imposed in the permissive policy.
- **Collision:** for each pair of runs belonging to the two collision task types in the cell, impose `e_i <= s_j OR e_j <= s_i`, including runs on different machines. Runs of the *same* task type are not serialized by this rule.
- **Deadline:** if the source gives a deadline for a request, every unit task ends at or before it. This is hard, not tardiness.
- **Horizon/availability:** integer slot times lie within the source horizon; no operation is preempted or allowed across a time leap.

Objective 1 minimizes `Cmax = max_i e_i`. Objective 2 is an epsilon-constraint trade-off: given a user-selected hard bound `Cmax <= B`, minimize `sum_i sum_(m,k in A_i) x_i,m,k * sum_t power_k[t]`. CP-SAT is integer-only: profile values are scaled by 1,000, and uploads requiring more than three decimal places are rejected for this objective instead of silently rounded. **This proxy ignores when the profiles run and is not the grid-price/PV score objective.**

For display, the separately computed source-style score is `sum_t max(0, sum_i assigned_profile_i(t) - solar[t]) * price[t]`. Mode profiles determine durations and raw score contributions; solar and price arrays do not otherwise constrain the makespan model. Physical energy and currency units are not independently verified; see [dataset notes](textile_dataset.md).

## Baseline and solver behavior

The comparison baseline is **deadline-first FIFO**: among precedence-ready runs, sort by source deadline (missing deadlines last), source request index, unit index, source task index and run index. For each task, use the feasible eligible machine/mode with earliest finish, breaking ties by start, machine ID and mode ID, accounting for the same selected policy, time leaps, collision, unit/machine occupancy and deadline. Its `HEURISTIC_FAILED` status is not an infeasibility proof.

Separately, to seed CP-SAT, four feasible load-biased dispatches are tried (biases 0.75, 1.0, 1.5, 2.0; skipped for over 500 runs). Their candidate score is `finish + bias × (already assigned machine busy slots + chosen duration + remaining single-machine mandatory slots)`. The best eligible candidate and the baseline are considered; the best under the chosen objective is provided as a **hint**, not a constraint or a substituted solver result. Each heuristic candidate and returned CP-SAT solution is checked by an independent validator.

`OPTIMAL` proves the selected objective for this formulated model. `FEASIBLE` is a valid incumbent with no optimality proof; its lower bound is shown separately. `INFEASIBLE` means CP-SAT proved the stated formulation infeasible. `UNKNOWN` means no schedule was returned before termination and is **not** proof of infeasibility. `MODEL_INVALID` and greedy failure are reported as such. The search limit applies to CP-SAT; warm-start/model construction is additional wall time.

## Measured benchmark: default JSON direction, conservative unit policy

Measured 2026-10-28 in the coding sandbox, Linux, Python 3.13.16, OR-Tools 9.15.6755, seed 0, one worker, 8-second CP-SAT wall limit. Both schedules use the **same** published input and constraints, and both pass the independent validator. [Machine-readable snapshot and schedules](../results/textile/) are included; they are computed schedules, not historical records. See `benchmark.json` for exact metadata and validation results.

| Measure | Deadline-first FIFO | CP-SAT incumbent | Change |
|---|---:|---:|---:|
| Solver status | HEURISTIC | FEASIBLE | Not proven optimal |
| Cmax, working slots | 1,016 | 834 | **17.91% lower** |
| Cmax, working minutes | 5,080 | 4,170 | 910 minutes lower |
| Elapsed calendar minutes, including overnight breaks | 7,480 | 6,090 | 1,390 minutes lower |
| Total mode profile, raw | 1,330,241 | 1,530,073 | **15.02% higher** |
| Grid draw, raw | 725,640.4 | 870,398.0 | **19.95% higher** |
| Source-style cost score, raw | 48.577031790 | 58.464284884 | **20.35% higher** |
| Mean machine utilization | 78.77% | 95.24% | +16.47 percentage points |
| Source deadline units met | 1 / 1 | 1 / 1 | — |

The CP-SAT lower bound was 587 slots, not a proven optimum. Its selected warm-start had Cmax 834, and in this recorded run the returned incumbent was also 834: the combined load-balanced warm-start/CP-SAT approach produced the difference versus FIFO; the solver did **not** improve on its warm-start in this snapshot. The faster schedule increases the source-style cost score and raw profile; **there is no claim of monetary or energy savings**. Positive percentage reduction is `(baseline - candidate) / baseline × 100`.

## Measured second objective: raw profile under a Cmax cap

With the same dataset/interpretations, seed, worker and 8-second limit, and hard `Cmax <= 1016`, the baseline also satisfies the cap. The profile-objective CP-SAT result was `FEASIBLE`, with profile sum **1,320,574** versus **1,330,241** for FIFO (0.73% lower); Cmax remained 1,016 slots. Its lower bound was 868,467 raw units. The source-style score was 47.921059038 versus 48.577031790 (1.35% lower), but that score was not the optimized objective, nor a verified monetary amount. [Snapshot and CSVs](../results/textile_profile/).

Recreate the snapshots (these overwrite their respective output directories; time-limited incumbents can differ across CPU/solver versions):

```bash
python scripts/benchmark_textile.py --seconds 8 --workers 1 --direction json
python scripts/benchmark_textile.py --seconds 8 --workers 1 --direction json \
  --objective profile --makespan-limit 1016 --output-dir results/textile_profile
```

For the paper direction, use `--direction paper`. For independent tasks within a unit, add `--allow-unit-overlap`. A baseline violating a selected profile cap is not shown as an equal-constraint comparison.

## Boundaries

This module does not implement time-dependent grid-score minimization, demand-response events, multi-cell balancing, setups, machine/operator availability other than source time leaps, interrupted tasks, material planning or textile-specific breakdown/urgent-order reoptimization. It rejects unknown source constraint types rather than silently ignoring them. The original synthetic workspace retains its separate aggregate planning, flexible scheduling and disruption reoptimization, with synthetic inputs clearly labeled. Do not interpret these calculations as a deployed factory system.
