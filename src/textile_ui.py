"""Real-data Streamlit workspace; synthetic workspace remains in app.py."""
from __future__ import annotations
import pandas as pd
import streamlit as st
from .textile_data import (DATASET_URL, INPUT_SHA256, PAPER_URL, TextileInputError,
                           download_published_input, load_published_bytes, parse_textile_json,
                           source_slot_label)
from .textile_dispatching import dispatch_textile
from .textile_gantt import textile_gantt
from .textile_metrics import compare_textile, textile_machine_metrics, textile_metrics
from .textile_scheduling import solve_textile
from .textile_validation import validate_textile_schedule


def _show_status(result):
    text = f"{result.status} · {result.message}"
    if result.status == 'OPTIMAL': st.success(text)
    elif result.status == 'FEASIBLE': st.info(text)
    elif result.status == 'INFEASIBLE': st.error(text)
    else: st.warning(text)
    st.caption(f"Total elapsed {result.solve_seconds:.2f}s (including model/warm-start construction); "
               f"CP-SAT limit {result.metadata.get('time_limit_seconds', 0):g}s; "
               f"{result.metadata.get('workers')} worker(s); seed {result.metadata.get('random_seed')}.")
    if result.has_schedule:
        st.caption(f"Objective: {result.objective} = {result.objective_value:,.3f}; "
                   f"solver lower bound = {result.best_bound:,.3f}. "
                   f"Warm start: {result.metadata.get('warm_start_source')} "
                   f"(Cmax {result.metadata.get('warm_start_makespan_slots')} slots).")


def _show_dataset(instance, provenance):
    st.caption(f"Input: {provenance} · SHA-256 `{instance.input_hash}`")
    a, b, c, d = st.columns(4)
    a.metric('Product units', f'{instance.total_units:,}')
    b.metric('Task runs', f'{len(instance.operations):,}')
    c.metric('Machines', len(instance.machines))
    d.metric('Horizon', f'{instance.horizon:,} slots')
    with st.expander('Machine compatibility, modes and requests'):
        mode_rows = []
        for task, ids in instance.task_modes.items():
            for mid in ids:
                machines = [machine for machine in instance.machines if mid in instance.machine_modes[machine]]
                mode = instance.modes[mid]
                mode_rows.append({'Task': task, 'Mode': mid, 'Eligible machines': ', '.join(machines) or 'none',
                                  'Duration (5-minute slots)': mode.duration,
                                  'Duration (minutes)': 5 * mode.duration,
                                  'Profile sum (raw units)': sum(mode.power)})
        st.dataframe(pd.DataFrame(mode_rows), hide_index=True, width='stretch')
        st.markdown('**Source product requests**')
        requests = pd.DataFrame(instance.requests).rename(columns={'request_id':'Request', 'product':'Product',
                                                                   'amount':'Units', 'deadline':'Deadline (slot)'})
        st.dataframe(requests, hide_index=True, width='stretch')
        st.caption('A request deadline applies to completion of the entire product unit. Blank means no source deadline.')
    for warning in instance.warnings: st.warning(warning)


def _assumptions(instance):
    with st.expander('Interpretation, limitations and published reference'):
        order = '; '.join(f'{a} → {b}' for a,b in instance.order_pairs) or 'none'
        collision = '; '.join(f'{a} ↔ {b}' for a,b in instance.collision_pairs) or 'none'
        st.markdown(f"""
- **Order selected:** {order}. The JSON names `first_task`/`second_task`; the paper describes the opposite direction for this dataset. The selector exposes both; an order applies within each product unit when both tasks are required. This scope is an explicit modeling assumption.
- **Task list:** required task runs, not an invented routing sequence. Same-unit policy selected: {'only one task at a time (conservative)' if instance.unit_exclusive else 'independent tasks may overlap'}. The accompanying statistics workbook shows four overlaps between rows sharing a product identifier. Identical repeated runs are ordered by start time only to break label symmetry.
- **Collision:** {collision}, enforced between different tasks anywhere in the shared cell. All tasks are non-interruptible and cannot cross a listed time-leap boundary; each must use an eligible machine/mode. Only source deadlines are imposed.
- **Energy / objective:** mode profile, solar and price arrays are used for the displayed source-style score `sum(max(0, total_profile[t] − solar[t]) × price[t])`. The optional profile objective minimizes the sum of selected mode profiles under a makespan cap; it does **not** minimize the time-dependent score. For the Zenodo case, the paper describes Wh per period but its reported PV capacity conflicts with the raw solar values. Neither physical kWh nor currency is verified; no energy or monetary savings claim is made.
- **Published output:** the Zenodo output JSON has mode IDs absent from the input. Its supplementary workbook supplies product-unit identifiers but not an unambiguous mapping to the two same-product requests; four overlapping same-unit row pairs violate the conservative policy. Its reported score 36.415593242 is a reference only, not an optimum or an equal-constraint benchmark.
- **Scope:** this is a computed schedule for the published case-study input, not a historical execution record. No real breakdowns, urgent customer orders, inventory, setups or dates are invented. Use the Synthetic factory workspace for its separate planning and disruption demonstrations.
""")
        st.markdown(f"Source: [Zenodo record]({DATASET_URL}) · [Companion paper]({PAPER_URL}) · "
                    "Mota, Gomes, Faria, Ramos and Vale (2020), MIT license. Attribution is included in `data/textile/ATTRIBUTION.txt`.")


def render_textile_workspace():
    st.markdown('<div class="eyebrow">REAL DATA / TEXTILE HANG-TAG LINE</div>', unsafe_allow_html=True)
    st.title('Schedule the textile line')
    st.markdown('<div class="muted">Reconstruct and optimize the published three-machine case study. '
                'Results are newly computed schedules, not recorded factory events.</div>', unsafe_allow_html=True)
    with st.expander('Dataset source and optional JSON upload'):
        st.markdown(f'[Zenodo record {DATASET_URL}]({DATASET_URL}) · MIT-licensed case-study input · '
                    f'[Companion article]({PAPER_URL})')
        uploaded = st.file_uploader('Upload compatible textile JSON (optional)', type=['json'], key='textile_upload')
        if st.button('Refresh verified input from Zenodo', key='textile_refresh'):
            try:
                download_published_input.cache_clear()
                st.session_state.textile_remote_blob = download_published_input()
                st.success('Verified Zenodo input refreshed and cached for this process.')
            except TextileInputError as exc:
                st.session_state.pop('textile_remote_blob', None)
                st.warning(f'{exc}. Using the bundled local copy if available.')
        st.caption('The bundled input works offline. Remote refresh is checksum-verified; unknown JSON fields and unsupported constraints are rejected.')
    direction_label = st.selectbox('Order interpretation',
        ('JSON field names: first → second', 'Paper narrative: second → first'),
        help='The published JSON field names and paper narrative disagree. This selection changes the enforced order.')
    direction = 'json' if direction_label.startswith('JSON') else 'paper'
    policy_label = st.selectbox('Same-unit task policy',
        ('Conservative: one task at a time per unit', 'Allow independent tasks of a unit to overlap'),
        help='The published statistics workbook contains overlapping tasks sharing a product identifier. '
             'Choose the conservative unit-resource assumption or allow independent requirements to overlap; '
             'machine and collision constraints always apply.')
    unit_exclusive = policy_label.startswith('Conservative')
    try:
        if uploaded is not None:
            blob, provenance = uploaded.getvalue(), f'Uploaded file: {uploaded.name}'
        elif 'textile_remote_blob' in st.session_state:
            blob, provenance = st.session_state.textile_remote_blob, 'Zenodo refresh (SHA-256 verified)'
        else:
            blob, provenance = load_published_bytes()
        instance = parse_textile_json(blob, direction, unit_exclusive=unit_exclusive)
    except TextileInputError as exc:
        st.error(f'Textile input rejected: {exc}')
        st.stop()
    _show_dataset(instance, provenance)
    if instance.input_hash == INPUT_SHA256:
        st.caption('Source calendar: six 07:00–23:00 working days, Monday through Saturday. '
                   'Slots are compressed across eight-hour overnight breaks; no calendar date is specified.')
    else:
        st.caption('Uploaded input: chart uses generic five-minute working slots; no calendar dates are inferred.')
    _assumptions(instance)

    st.subheader('Optimize the schedule')
    c1, c2, c3 = st.columns([2.4, 1.0, 1.0])
    objective_label = c1.selectbox('Objective', ('Minimize makespan', 'Minimize total mode profile under a makespan cap'))
    seconds = c2.number_input('CP-SAT time limit (seconds)', min_value=1, max_value=120, value=8, step=1, key='textile_seconds')
    workers = c3.number_input('Search workers', min_value=1, max_value=8, value=1, step=1, key='textile_workers')
    objective = 'makespan' if objective_label == 'Minimize makespan' else 'profile'
    cap = None
    if objective == 'profile':
        cap = int(st.number_input('Makespan cap (working slots)', min_value=1, max_value=instance.horizon,
                                  value=instance.horizon, step=1, key='textile_cap_' + instance.input_hash[:12]))
        st.caption('Epsilon-constraint trade-off: the cap is hard. Profile sums are an energy proxy in raw source units, not grid cost or kWh.')
    st.caption('Baseline: deadline-first FIFO, then earliest-finish eligible mode. Before CP-SAT, up to four additional load-balanced '
               'dispatches (for at most 500 runs) provide a validated warm start; the baseline remains unchanged. Solver seed is 0.')
    case_key = (instance.input_hash, direction, unit_exclusive, objective, cap, seconds, workers)
    if st.session_state.get('textile_case_key') != case_key:
        st.session_state.textile_case_key = case_key
        st.session_state.pop('textile_result', None)
        st.session_state.pop('textile_baseline', None)
    if st.button('Run textile optimization', type='primary', key='solve_textile'):
        try:
            with st.spinner('Building a validated baseline and solving the real-data model…'):
                baseline = dispatch_textile(instance)
                result = solve_textile(instance, time_limit=float(seconds), workers=int(workers), baseline=baseline,
                                       objective=objective, makespan_limit=cap)
            st.session_state.textile_baseline = baseline
            st.session_state.textile_result = result
        except (ValueError, RuntimeError) as exc:
            st.error(f'Could not solve textile model: {exc}')
    result = st.session_state.get('textile_result')
    baseline = st.session_state.get('textile_baseline')
    if result is None:
        st.info('Choose an interpretation and objective, then run optimization to generate a validated schedule.')
        return
    _show_status(result)
    if not result.has_schedule:
        if baseline and baseline.has_schedule:
            st.caption('A heuristic baseline exists, but it is not substituted for the solver result.')
        return
    errors = validate_textile_schedule(instance, result.schedule, makespan_limit=cap)
    if errors:
        st.error('Independent validation failed: ' + '; '.join(errors[:5]))
        return
    st.success('Independent validation passed: task coverage, eligibility, duration, calendar, deadlines, '
               'machine exclusivity, selected unit policy, order and collision.')
    m = textile_metrics(instance, result.schedule)
    a, b, c, d = st.columns(4)
    a.metric('Completion / Cmax', f"{m['makespan_slots']:,} slots", f"{m['makespan_working_minutes']:,} working min")
    b.metric('Source-style cost score', f"{m['source_style_cost_score']:.4f}", help='Raw source-style score; currency and physical units are not independently verified.')
    c.metric('Total mode profile', f"{m['total_profile_raw']:,.0f} raw")
    d.metric('Source deadlines met', f"{m['deadline_units_on_time']} / {m['deadline_units']}")
    if m['calendar_elapsed_minutes'] is not None:
        st.caption(f"Elapsed calendar time from Monday 07:00: {m['calendar_elapsed_minutes']/60:,.1f} hours (includes overnight breaks).")
    st.subheader('Actual returned machine schedule')
    st.plotly_chart(textile_gantt(instance, result.schedule), width='stretch', key='textile_gantt')
    st.caption(('Grey bands are overnight breaks in the published calendar. ' if instance.input_hash == INPUT_SHA256 else '') +
               'Hover for product unit, mode, task and exact endpoints.')
    table = result.schedule.copy()
    if instance.input_hash == INPUT_SHA256:
        table['start_display'] = table.start_slot.map(lambda x: source_slot_label(int(x)))
        table['end_display'] = table.end_slot.map(lambda x: source_slot_label(int(x), end=True))
    table['order_interpretation'] = instance.order_interpretation
    table['unit_exclusive'] = instance.unit_exclusive
    table['input_sha256'] = instance.input_hash
    st.dataframe(table, hide_index=True, width='stretch', height=410)
    st.download_button('Download validated textile schedule CSV', table.to_csv(index=False).encode('utf-8'),
                       file_name='textile_schedule.csv', mime='text/csv')
    st.subheader('Machine utilization')
    st.dataframe(textile_machine_metrics(instance, result.schedule), hide_index=True, width='stretch')
    st.caption('Utilization = occupied working slots ÷ Cmax, per machine; overnight gaps are excluded.')
    st.subheader('Baseline comparison')
    if baseline and baseline.has_schedule and not validate_textile_schedule(instance, baseline.schedule, makespan_limit=cap):
        st.dataframe(compare_textile(instance, baseline.schedule, result.schedule), hide_index=True, width='stretch')
        st.caption('Both schedules were independently validated against the same source constraints and any selected makespan cap. '
                   'Positive reduction means a lower value; negative means an increase. Solar use and utilization are not treated as reduction objectives.')
        baseline_export = baseline.schedule.assign(order_interpretation=instance.order_interpretation,
                                                   unit_exclusive=instance.unit_exclusive, input_sha256=instance.input_hash)
        st.download_button('Download baseline CSV', baseline_export.to_csv(index=False).encode('utf-8'),
                           file_name='textile_deadline_fifo_baseline.csv', mime='text/csv')
    elif baseline and baseline.has_schedule:
        st.warning('The baseline exceeds the selected makespan cap, so it is not a valid comparator under this profile-objective model.')
    else:
        st.warning('The baseline heuristic failed to construct a schedule; this is not a proof that the model is infeasible.')
