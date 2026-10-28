# Validation report

Executed on 2026-10-28 in the supplied Linux environment using Python 3.13.16, OR-Tools 9.15.6755, PuLP 3.2.2, Pandas 2.2.3, Streamlit 1.66.1 and pytest 9.0.3.

## Textile integration verification (2026-10-28)

The full updated repository suite ran with `pytest -q`: **57 passed in 27.78s**. This includes the original synthetic regressions and new tests for pinned input/checksums, remote caching/fallback, malformed/unsupported input, both disputed order directions and both unit policies, machine/mode compatibility, same-type and cross-type collision behavior, precedence, non-overlap, repeated runs, time leaps, hard deadlines, infeasibility, both objectives with hand-checkable optima, independently computed KPIs, persisted benchmark CSVs, Gantt endpoints, and Streamlit real/synthetic mode navigation and solves.

`python scripts/smoke_ui.py` passed real-data startup and the original synthetic planning, scheduling, Gantt, breakdown, urgent-order, comparison and capacity pages. `python -m pip check` passed; the Streamlit server bound to `0.0.0.0:8501`, with `/` and `/_stcore/health` returning HTTP 200. The published JSON/workbook audit was run against the downloaded, checksummed reference files. No deployment or Windows runtime verification was performed in this integration run.

## Earlier synthetic-only snapshot

The following is the previous 31-test synthetic report and is retained for historical context, not the current total.

## Automated tests

Command: `pytest -q`

```text
...............................                                          [100%]
31 passed in 8.65s
```

All 31 collected test cases passed in this run:

- PASS `tests/test_constraints.py::test_fixed_setup_occupies_machine_and_increases_duration`
- PASS `tests/test_constraints.py::test_machine_eligibility_alternatives_and_downtime`
- PASS `tests/test_constraints.py::test_calendar_shift_and_overlap_validation`
- PASS `tests/test_constraints.py::test_weighted_tardiness_objective_and_priorities`
- PASS `tests/test_constraints.py::test_input_validation_and_expansion`
- PASS `tests/test_constraints.py::test_validator_detects_machine_overlap_and_precedence`
- PASS `tests/test_constraints.py::test_nonpreemptive_operation_cannot_cross_planned_maintenance`
- PASS `tests/test_input_validation.py::test_sample_csv_roundtrip_is_compatible`
- PASS `tests/test_input_validation.py::test_duplicate_order_and_invalid_priority_rejected`
- PASS `tests/test_input_validation.py::test_cross_resource_alternatives_are_rejected`
- PASS `tests/test_input_validation.py::test_sample_cp_sat_returns_and_validates_feasible_incumbent`
- PASS `tests/test_input_validation.py::test_unknown_status_is_not_feasible`
- PASS `tests/test_input_validation.py::test_exported_schedule_can_be_reloaded_and_validated`
- PASS `tests/test_phase1.py::test_manual_optimum`
- PASS `tests/test_phase1.py::test_sample_baselines_are_complete_and_valid`
- PASS `tests/test_phase1.py::test_infeasible_not_reported_as_feasible`
- PASS `tests/test_phase3.py::test_gantt_exactly_matches_schedule_and_idle_is_not_work`
- PASS `tests/test_phase3.py::test_metrics_are_derived_from_finish_times`
- PASS `tests/test_planning.py::test_shortage_prioritization_and_integration`
- PASS `tests/test_planning.py::test_aggregate_plan_does_not_prove_scheduling_feasibility`
- PASS `tests/test_planning.py::test_zero_material_can_produce_empty_schedule_scope`
- PASS `tests/test_planning.py::test_planned_batch_size_controls_processing_time`
- PASS `tests/test_rescheduling.py::test_breakdown_aborts_and_restarts_full_operation`
- PASS `tests/test_rescheduling.py::test_completed_and_running_operations_are_frozen_for_urgent_order`
- PASS `tests/test_rescheduling.py::test_breakdown_freezes_completed_and_other_running_work`
- PASS `tests/test_rescheduling.py::test_breakdown_can_be_proven_infeasible`
- PASS `tests/test_sample_exports.py::test_bundled_full_demand_schedule_exports_are_feasible`
- PASS `tests/test_sample_exports.py::test_bundled_breakdown_and_urgent_schedule_exports`
- PASS `tests/test_sample_exports.py::test_bundled_capacity_scenario_schedule_is_feasible`
- PASS `tests/test_sample_exports.py::test_offline_html_contains_exact_exported_operation_bars`
- PASS `tests/test_streamlit_app.py::test_app_navigation_baselines_and_gantt`

These include the manually checkable two-job optimum (Cmax = 8), valid and proven-infeasible cases, eligible alternative machines and maintenance, fixed setup occupancy, precedence and no-overlap checks, planning/scheduling integration, breakdown restart and preservation, urgent orders, metrics, exact Gantt-to-schedule matching (including the offline HTML), sample-export validation, and Streamlit navigation.

## Application smoke test

`python scripts/smoke_ui.py` passed through factory setup, a 574-unit material plan, applying planned quantities, CP-SAT optimization, the Gantt, breakdown re-optimization, urgent-order re-optimization, shift-capacity what-if and model-configuration pages. The sample optimization and revisions returned `FEASIBLE`, not `OPTIMAL`, under the smoke test's 4-second limits. The actual Streamlit server was also started on `0.0.0.0:8501`; HTTP health and root endpoints returned 200, and the preview WebSocket connected. Input CSV regeneration was byte-for-byte deterministic.

This is a record of the executed synthetic example, not a proof of correctness for all possible inputs. Time-limited solver statuses may change on other machines; sample-export tests skip optional scenario exports if no incumbent is returned when a snapshot is regenerated.
