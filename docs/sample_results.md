# Sample results — synthetic factory

These are **measured outputs of one local run**, not claims about a real factory. Data are generated with seed 41. Environment: Python 3.13.16, OR-Tools 9.15.6755, PuLP 3.2.2, Pandas 2.2.3. The CP-SAT runs below used one worker, seed 41, and an 8-second limit per solve; wall-clock-limited incumbents and bounds can vary by computer, dependency version and run. Reproduce with `python scripts/run_sample.py`. All returned schedules were checked by the independent validator.

Factory origin: 2026-11-02 00:00 local; horizon: 20160 minutes; 24 orders, 6 machines, 6 products. Cmax is minutes from the origin, including nonworking time. Tardiness is also in minutes. Weighted tardiness is Σ(priority × tardiness).

## Dispatch rules and optimizer

| Method | Status | Cmax | Total tardiness | Weighted tardiness | Late orders | Best objective bound |
| --- | --- | --- | --- | --- | --- | --- |
| FIFO | HEURISTIC | 3464 | 8056 | 11809 | 9 | — |
| EDD | HEURISTIC | 3463 | 37 | 37 | 2 | — |
| SPT | HEURISTIC | 3567 | 5749 | 8145 | 6 | — |
| CP-SAT makespan | FEASIBLE | 2446 | 2227 | 3389 | 4 | 2,200 |
| CP-SAT weighted_tardiness | FEASIBLE | 2452 | 0 | 0 | 0 | 2,200 |

A **FEASIBLE** result is not proven optimal; dispatch rules are heuristics. The best bound belongs to the solver's raw selected objective, not always to Cmax alone. For weighted tardiness the raw objective is `(H+1) × weighted tardiness + Cmax`. Comparison does not imply every metric improves.

## Dynamic rescheduling

Both scenarios start from the **same EDD schedule**. At minute 700 (2026-11-02 11:40), M01 breaks down through minute 880. The operation running on M01 is aborted and restarted in full on M01 after repair; other running and completed operations are fixed. The separate urgent scenario inserts `URG-001` (P-A, quantity 8, priority 5, release 700, due 1600); material availability for it is assumed, not planned. Both use the documented stability objective, not the baseline EDD rule.

| Scenario | Status | Original Cmax | Revised Cmax | Original weighted tardiness | Revised weighted tardiness | Newly late existing orders | Machine changes | Aborted min |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Breakdown | FEASIBLE | 3463 | 3490 | 37 | 45 | 0 | 6 | 17 |
| Urgent order | FEASIBLE | 3463 | 3490 | 37 | 160 | 2 | 4 | 0 |

The urgent scenario contains an additional order and therefore its total tardiness is not a like-for-like comparison of the original 24 orders. Newly late counts only original orders that were on time before and late afterward.

## Aggregate production planning

Status **OPTIMAL**; available material 574 units, used 574; demand 280 units, planned 254, unmet 26; objective 8808.00 cost units. This is an aggregate plan, not a scheduling-feasibility proof.

## Capacity what-if

Status: **FEASIBLE**. M06's shift is extended from 17:00 to 18:00, adding 600 available minutes over the horizon. Weighted tardiness changed from 0 to 0; makespan changed from 2452 to 2405 minutes. At hypothetical rates of 12 cost units per added available hour and 1 cost unit per weighted tardy minute, the estimated net is -120.00 cost units (capacity cost 120.00; delay-cost saving 0.00).

The cost rates are illustrative, not observed savings. The comparison uses the two returned weighted-tardiness incumbents; if either is only FEASIBLE, it does not prove the best achievable benefit of the extension. Cost is charged on all additional available hours over the horizon, not just used hours, and excludes other financial effects.

## Files

`results/` contains the exported schedules, plan, interrupted-history CSV where applicable, and `sample_gantt.html`, an offline interactive chart generated from the selected sample schedule. Solver results may differ from this snapshot when regenerated.
