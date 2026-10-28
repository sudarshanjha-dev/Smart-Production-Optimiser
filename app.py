"""Streamlit UI. Optimization and validation live in src/, not in this file."""
from __future__ import annotations
from datetime import datetime, time, timedelta
from pathlib import Path
import pandas as pd
import streamlit as st

from src.capacity_analysis import cost_estimate, extend_machine_shift
from src.calendars import available_minutes
from src.data_loader import COLUMNS, InputError, build_operations, load_sample, make_factory
from src.dispatching_rules import dispatch_schedule
from src.gantt_chart import make_gantt
from src.production_planning import factory_from_plan, plan_production
from src.rescheduling import reschedule_breakdown, reschedule_urgent_order
from src.schedule_metrics import compare_schedules, machine_workload, order_metrics, summary_metrics
from src.schedule_validator import validate_schedule
from src.scheduling_model import solve_schedule
from src.textile_ui import render_textile_workspace

st.set_page_config(page_title="Smart Production Optimizer", page_icon="⚙️", layout="wide", initial_sidebar_state="expanded")
st.markdown("""
<style>
  .block-container {max-width: 1450px; padding-top: 2rem; padding-bottom: 3rem;}
  h1, h2, h3 {letter-spacing: -0.025em;}
  h1 {font-weight: 720; font-size: 2.15rem !important;}
  h3 {font-size: 1.12rem !important;}
  [data-testid="stSidebar"] {background: #102e2b;}
  [data-testid="stSidebar"] * {color: #e4f2ed;}
  [data-testid="stSidebar"] [data-baseweb="radio"] label {padding: 4px 0;}
  [data-testid="stMetric"] {background: white; border: 1px solid #dce7e3; border-radius: 12px; padding: 14px 17px;}
  [data-testid="stMetricLabel"] {color: #647c76;}
  [data-testid="stMetricValue"] {font-size: 1.5rem; color: #123e36;}
  [data-testid="stDataFrame"] {border: 1px solid #e1eae7; border-radius: 8px;}
  .eyebrow {font-size: 0.7rem; letter-spacing: .15em; font-weight: 750; color: #287e6f; text-transform: uppercase; margin-bottom: .25rem;}
  .muted {color: #607873; font-size: .94rem; line-height: 1.5;}
  .callout {border-left: 3px solid #43a68f; padding: .65rem 1rem; background:#edf6f2; border-radius: 0 8px 8px 0; color:#315d53; margin: .7rem 0 1rem;}
  .brand {font-weight: 800; line-height: 1.2; letter-spacing: -.02em; font-size: 1.15rem; color:#fff;}
  .brand-sub {font-size: .68rem; letter-spacing: .14em; color:#a4c9bf; margin: .4rem 0 1.3rem;}
  div.stButton > button[kind="primary"] {background:#176b5b; border:1px solid #176b5b;}
</style>
""", unsafe_allow_html=True)

PAGES = ["Factory Setup", "Production Planning", "Scheduling", "Gantt Chart", "Rescheduling", "Schedule Comparison", "Model Configuration"]
if "factory" not in st.session_state:
    st.session_state.factory = load_sample()
    st.session_state.active_factory = st.session_state.factory
    st.session_state.active_source = "Original demand"
    st.session_state.plan = None
    st.session_state.runs = {}
    st.session_state.last_run = None
    st.session_state.revision = None
    st.session_state.capacity_result = None
    st.session_state.factory_version = 0


def reset_factory(factory):
    st.session_state.factory = factory
    st.session_state.active_factory = factory
    st.session_state.active_source = "Original demand"
    st.session_state.plan = None
    st.session_state.runs = {}
    st.session_state.last_run = None
    st.session_state.revision = None
    st.session_state.capacity_result = None
    st.session_state.factory_version += 1


def apply_scope(factory, label):
    st.session_state.active_factory = factory
    st.session_state.active_source = label
    st.session_state.runs = {}
    st.session_state.last_run = None
    st.session_state.revision = None
    st.session_state.capacity_result = None


def heading(kicker, title, description):
    st.markdown(f'<div class="eyebrow">{kicker}</div>', unsafe_allow_html=True)
    st.title(title)
    st.markdown(f'<div class="muted">{description}</div>', unsafe_allow_html=True)
    st.write("")


def clock(factory, minute):
    return (factory.origin + timedelta(minutes=int(minute))).strftime("%d %b %Y, %H:%M")


def csv_bytes(frame):
    return frame.to_csv(index=False).encode("utf-8")


def record_run(label, factory, result):
    if result.has_schedule:
        problems = validate_schedule(factory, result.schedule, result.history)
        if problems:
            raise RuntimeError("Schedule validation failed: " + "; ".join(problems[:5]))
    st.session_state.runs[label] = {"factory": factory, "result": result}
    st.session_state.last_run = label


def status_note(result):
    if result.status == "OPTIMAL":
        st.success(f"OPTIMAL · Proven optimal for the stated objective in {result.solve_seconds:.2f} s.")
    elif result.status == "FEASIBLE":
        st.info(f"FEASIBLE · A valid incumbent was found in {result.solve_seconds:.2f} s; optimality is not proven.")
    elif result.status == "HEURISTIC":
        st.info("HEURISTIC · Feasible dispatch-rule schedule; no optimality proof.")
    elif result.status == "INFEASIBLE":
        st.error("INFEASIBLE · The solver proved there is no schedule under these constraints and horizon.")
    else:
        st.warning(f"{result.status} · {result.message} (not a proof of infeasibility unless status is INFEASIBLE).")


def result_metrics(factory, result):
    data = summary_metrics(factory, result.schedule, result.history)
    a, b, c, d = st.columns(4)
    a.metric("Makespan / Cmax", f"{data['makespan']:,} min", help="Maximum completion time measured from the factory origin; includes calendar gaps.")
    b.metric("Weighted tardiness", f"{data['weighted_tardiness']:,} min", help="Sum of each order's tardiness times its priority.")
    c.metric("Late orders", f"{data['late_orders']} / {data['order_count']}")
    d.metric("Scheduled busy time", f"{data['scheduled_busy_minutes']:,} min", help="Setup plus processing; aborted work is reported separately.")


def schedule_table(result):
    return result.schedule.sort_values(["machine_id", "start", "operation_id"]).reset_index(drop=True)


def baseline_runs(factory):
    for rule in ("FIFO", "EDD", "SPT"):
        record_run(rule, factory, dispatch_schedule(factory, rule))


with st.sidebar:
    st.markdown('<div class="brand">◫ &nbsp; Production<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; Optimizer</div><div class="brand-sub">PLANNING / SCHEDULING</div>', unsafe_allow_html=True)
    workspace = st.selectbox("Dataset", ("Real textile case study", "Synthetic factory"),
                             help="Switch between the published textile input and the original synthetic planning workspace.")
    st.divider()
    if workspace == "Synthetic factory":
        page = st.radio("WORKSPACE", PAGES, label_visibility="collapsed")
        st.divider()
        active = st.session_state.active_factory
        st.caption("ACTIVE FACTORY")
        st.markdown(f"**{len(active.orders)} orders** · {len(active.machines)} machines")
        st.caption(st.session_state.active_source)
        st.caption(f"Origin: {active.origin:%d %b %Y} · Horizon: {active.horizon // 1440} days")
        st.markdown("<br>", unsafe_allow_html=True)
        st.caption("Synthetic example · local decision-support tool")
    else:
        st.caption("ZENODO CASE STUDY")
        st.markdown("**Textile hang-tag line** · 3 machines")
        st.caption("Real case-study input · schedules are computed, not historical execution records")

if workspace == "Real textile case study":
    render_textile_workspace()
    st.stop()

if page == "Factory Setup":
    factory = st.session_state.factory
    heading("01 / factory setup", "Configure the factory", "Define orders, machine shifts and product routings. The bundled factory is synthetic and ready to schedule.")
    a, b, c, d = st.columns(4)
    a.metric("Production orders", len(factory.orders))
    b.metric("Machines", len(factory.machines))
    c.metric("Products", len(factory.products))
    d.metric("Routed operations", len(build_operations(factory)))
    st.markdown('<div class="callout"><b>Time convention</b> &nbsp; All inputs are integer minutes from the factory-local origin, including overnight and weekends. Intervals are [start, finish). Priorities run from 1 (low) to 5 (high).</div>', unsafe_allow_html=True)
    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("Reset to sample factory", width="stretch"):
            reset_factory(load_sample())
            st.rerun()
    with col2:
        st.caption("Changes invalidate previous plans and schedules. Edit the tables below or upload compatible CSVs.")
    with st.expander("Edit factory tables and time settings", expanded=False):
        with st.form("edit_factory", clear_on_submit=False):
            c1, c2 = st.columns(2)
            origin_date = c1.date_input("Factory origin date (00:00 local)", value=factory.origin.date())
            horizon_days = c2.number_input("Scheduling horizon (calendar days)", min_value=1, max_value=90, value=max(1, factory.horizon // 1440), step=1)
            names = [("orders", "Orders"), ("machines", "Machines & shifts"), ("products", "Products & costs"), ("routings", "Routings"), ("downtimes", "Maintenance")]
            tabs = st.tabs([name for _, name in names])
            edited = {}
            for (key, _), tab in zip(names, tabs):
                with tab:
                    edited[key] = st.data_editor(getattr(factory, key), num_rows="dynamic", width="stretch",
                                                  key=f"edit_{key}_{st.session_state.factory_version}")
            st.caption("One routing row per eligible machine. Alternatives for an operation must share a resource group. Weekdays: 0=Monday … 6=Sunday, separated by |.")
            submitted = st.form_submit_button("Validate and apply edits", type="primary")
            if submitted:
                try:
                    new_factory = make_factory(**edited, origin=datetime.combine(origin_date, time.min), horizon=int(horizon_days) * 1440)
                    reset_factory(new_factory)
                    st.rerun()
                except (InputError, ValueError, TypeError) as exc:
                    st.error(str(exc))
    with st.expander("Upload compatible CSV files"):
        st.caption("Supply all four required files; downtime is optional. The current origin and horizon are retained. Download sample templates below for the exact schema.")
        cols = st.columns(5)
        uploads = {}
        for col, key in zip(cols, ["orders", "machines", "products", "routings", "downtimes"]):
            with col:
                uploads[key] = st.file_uploader(f"{key}{' (optional)' if key == 'downtimes' else ''}", type="csv", key=f"upload_{key}")
        if st.button("Load and validate uploaded files"):
            if any(uploads[k] is None for k in ("orders", "machines", "products", "routings")):
                st.error("Orders, machines, products, and routings CSVs are required together.")
            else:
                try:
                    tables = {k: pd.read_csv(v, dtype={"working_days": str} if k == "machines" else None) if v is not None else pd.DataFrame(columns=COLUMNS[k]) for k, v in uploads.items()}
                    reset_factory(make_factory(**tables, origin=factory.origin, horizon=factory.horizon))
                    st.rerun()
                except (InputError, ValueError, TypeError, pd.errors.ParserError) as exc:
                    st.error(f"Could not load factory: {exc}")
    with st.expander("Download sample CSV templates"):
        cols = st.columns(5)
        for col, key in zip(cols, COLUMNS):
            with col:
                data = (Path(__file__).parent / "data" / f"{key}.csv").read_bytes()
                st.download_button(f"{key}.csv", data, f"{key}.csv", "text/csv", width="stretch")
    st.subheader("Current orders")
    st.dataframe(factory.orders, hide_index=True, width="stretch")

elif page == "Production Planning":
    factory = st.session_state.factory
    heading("02 / production planning", "Decide production quantities", "Solve an aggregate integer model before detailed scheduling. Shortages are permitted and penalized according to order priority.")
    st.markdown('<div class="callout"><b>Planning is not scheduling.</b> Resource-group capacity is an optimistic aggregate bound. A planned quantity must still pass the detailed calendar and sequencing model.</div>', unsafe_allow_html=True)
    product_data = factory.products.set_index("product_id")
    full_material = int(sum(int(o.quantity) * int(product_data.loc[o.product_id, "material_per_unit"]) for o in factory.orders.itertuples(index=False)))
    c1, c2, c3 = st.columns([1, 1, 1])
    stock = c1.number_input("Available raw material units", min_value=0, max_value=10_000_000, value=min(10_000_000, int(full_material * .85)), step=1)
    factor = c2.slider("Usable aggregate capacity (%)", min_value=10, max_value=100, value=100, step=5)
    c3.metric("Material for full demand", f"{full_material:,} units")
    st.caption("Cost unit is arbitrary. No inventory or time-phased material arrivals are modeled. The planner ignores order due dates.")
    if st.button("Optimize production quantities", type="primary"):
        with st.spinner("Solving the production planning MILP…"):
            st.session_state.plan = plan_production(factory, int(stock), factor / 100)
    plan = st.session_state.plan
    if plan is not None:
        if not plan.has_plan:
            st.warning(f"Planning status: {plan.status}. {plan.message}")
        else:
            st.success(f"{plan.status} · Minimum cost = {plan.objective_value:,.2f} cost units. Material used: {plan.material_used:,} / {plan.material_limit:,}.")
            m1, m2, m3 = st.columns(3)
            m1.metric("Demand", int(plan.order_plan.demand_quantity.sum()))
            m2.metric("Planned", int(plan.order_plan.planned_quantity.sum()))
            m3.metric("Unmet demand", int(plan.order_plan.shortage_quantity.sum()))
            tab1, tab2 = st.tabs(["Quantities by order", "Aggregate resource capacity"])
            with tab1:
                st.dataframe(plan.order_plan, hide_index=True, width="stretch")
                st.download_button("Download quantity plan CSV", csv_bytes(plan.order_plan), "quantity_plan.csv", "text/csv")
            with tab2:
                st.dataframe(plan.capacity, hide_index=True, width="stretch")
                st.caption("Load uses the smallest eligible processing time and smallest setup for each operation. Those minima may come from different machines.")
            c1, c2 = st.columns(2)
            if c1.button("Use planned quantities for scheduling", type="primary", width="stretch"):
                apply_scope(factory_from_plan(factory, plan), "Production plan quantities")
                st.rerun()
            if c2.button("Use original demand instead", width="stretch"):
                apply_scope(factory, "Original demand")
                st.rerun()
            st.caption(f"Active scheduling scope: {st.session_state.active_source} · {len(st.session_state.active_factory.orders)} orders. Applying a scope clears earlier schedules.")

elif page == "Scheduling":
    factory = st.session_state.active_factory
    heading("03 / scheduling", "Generate a production schedule", "Assign every routed operation to an eligible machine, then sequence it within shifts and maintenance windows.")
    st.caption(f"SCHEDULING SCOPE: {st.session_state.active_source.upper()}  ·  {len(factory.orders)} orders  ·  {len(build_operations(factory))} operations")
    if factory.orders.empty:
        st.warning("No positive planned quantities. Change the production plan or restore original demand first.")
    else:
        c1, c2 = st.columns([2, 1])
        objective_label = c1.selectbox("Optimization objective", ["Minimum makespan", "Minimum weighted tardiness, then makespan"])
        seconds = c2.slider("CP-SAT time limit (seconds)", min_value=3, max_value=60, value=8, step=1)
        st.caption("Makespan focuses on finishing the whole workload; weighted tardiness favors the due dates of high-priority orders. The second objective uses makespan as a strict tie-breaker.")
        x, y = st.columns([1, 1])
        if x.button("Run CP-SAT optimization", type="primary", width="stretch"):
            with st.spinner("Building and solving the scheduling model…"):
                baseline_runs(factory)
                objective = "makespan" if objective_label == "Minimum makespan" else "weighted_tardiness"
                result = solve_schedule(factory, objective, time_limit=seconds)
                label = "Optimized · makespan" if objective == "makespan" else "Optimized · weighted tardiness"
                record_run(label, factory, result)
        if y.button("Generate dispatching baselines only", width="stretch"):
            with st.spinner("Constructing FIFO, EDD and SPT schedules…"):
                baseline_runs(factory)
        if st.session_state.last_run:
            label = st.session_state.last_run
            run = st.session_state.runs[label]
            result, run_factory = run["result"], run["factory"]
            st.subheader(f"Latest run · {label}")
            status_note(result)
            if result.has_schedule:
                result_metrics(run_factory, result)
                if result.objective_value is not None:
                    st.caption(f"Solver objective value: {result.objective_value:,.0f}  ·  Best bound: {result.best_bound:,.0f}  ·  Objective: {result.objective}")
                st.dataframe(schedule_table(result), hide_index=True, width="stretch", height=390)
                st.download_button("Download machine-wise schedule CSV", csv_bytes(schedule_table(result)), "machine_schedule.csv", "text/csv")
                st.caption("Open Gantt Chart for the timeline, or Rescheduling to simulate a disruption.")

elif page == "Gantt Chart":
    heading("04 / machine-wise gantt", "Inspect the production sequence", "Every bar comes directly from the selected computed schedule. Filter without changing the underlying plan.")
    valid = {k: v for k, v in st.session_state.runs.items() if v["result"].has_schedule}
    if not valid:
        st.info("Generate an optimized or dispatch-rule schedule on the Scheduling page first.")
    else:
        keys = list(valid)
        default = keys.index(st.session_state.last_run) if st.session_state.last_run in keys else 0
        label = st.selectbox("Schedule", keys, index=default)
        run = valid[label]; factory, result = run["factory"], run["result"]
        st.caption(f"{result.status} · {len(result.schedule)} scheduled operations · minutes are measured from {factory.origin:%d %b %Y 00:00} factory time.")
        a, b = st.columns(2)
        machines = a.multiselect("Machines (empty = all)", factory.machines.machine_id.tolist())
        orders = b.multiselect("Orders (empty = all)", sorted(factory.orders.order_id.tolist()))
        c, d = st.columns(2)
        idle = c.checkbox("Show available idle periods", value=True)
        blocked = d.checkbox("Show unavailable / off-shift periods", value=True)
        figure = make_gantt(factory, result.schedule, result.history, machines or None, orders or None, idle, blocked)
        st.plotly_chart(figure, width="stretch", config={"displaylogo": False})
        st.caption("Grey-green = available but idle; pale grey = off shift or unavailable; hatched orange = interrupted work discarded before restart. Idle is calculated using the full schedule, even when orders are filtered.")
        table = schedule_table(result)
        if machines: table = table[table.machine_id.isin(machines)]
        if orders: table = table[table.order_id.isin(orders)]
        st.dataframe(table, hide_index=True, width="stretch", height=360)
        st.download_button("Download selected schedule CSV", csv_bytes(table), "gantt_schedule.csv", "text/csv")

elif page == "Rescheduling":
    heading("05 / disruption response", "Re-optimize after a disruption", "Freeze executed work, update constraints, and solve the remaining problem again. This is a new optimization, not a chart redraw.")
    valid = {k: v for k, v in st.session_state.runs.items() if v["result"].has_schedule and not v["result"].metadata.get("scenario")}
    if not valid:
        st.info("Generate a schedule on the Scheduling page before simulating a disruption.")
    else:
        keys = list(valid)
        preferred = next((x for x in reversed(keys) if x.startswith("Optimized")), keys[-1])
        base_label = st.selectbox("Original schedule", keys, index=keys.index(preferred))
        run = valid[base_label]; factory, base = run["factory"], run["result"].schedule
        default_now = min(factory.horizon - 1, max(0, int(base.start.min()) + 200))
        c1, c2, c3 = st.columns([1, 1, 1])
        mode = c1.selectbox("Scenario", ["Machine breakdown", "Urgent order"])
        now = int(c2.number_input("Decision time (minute)", min_value=0, max_value=factory.horizon - 1, value=default_now, step=1))
        seconds = c3.slider("Re-optimization limit (seconds)", 3, 60, 8, 1, key="resched_limit")
        st.caption(f"Decision time: {clock(factory, now)}. Completed operations and unaffected operations already running at this instant remain fixed.")
        if mode == "Machine breakdown":
            running = base[(base.start < now) & (base.finish > now)]
            ids = factory.machines.machine_id.tolist()
            default_machine = running.iloc[0].machine_id if not running.empty else ids[0]
            c1, c2 = st.columns(2)
            machine = c1.selectbox("Broken machine", ids, index=ids.index(default_machine))
            duration = int(c2.number_input("Breakdown duration (minutes)", min_value=1, max_value=factory.horizon - now, value=min(180, factory.horizon - now), step=1))
            end = now + duration
            affected = base[(base.machine_id == machine) & (base.start < end) & (base.finish > now)]
            running_broken = affected[(affected.start < now) & (affected.finish > now)]
            st.markdown(f'<div class="callout"><b>Restart policy:</b> {len(affected)} original operation(s) overlap this breakdown; {len(running_broken)} are already running on the broken machine. Interrupted work is discarded and restarted in full, on the same machine, after repair at {clock(factory, end)}.</div>', unsafe_allow_html=True)
            if not affected.empty:
                with st.expander("View directly affected operations"):
                    st.dataframe(affected[["operation_id", "order_id", "machine_id", "start", "finish"]], hide_index=True, width="stretch")
            if st.button("Simulate breakdown & re-optimize", type="primary"):
                try:
                    with st.spinner("Freezing history and solving the disrupted schedule…"):
                        revised_factory, result = reschedule_breakdown(factory, base, machine, now, end, seconds)
                        record_run("Revised · breakdown", revised_factory, result)
                        st.session_state.revision = {"original": base_label, "revised": "Revised · breakdown"}
                except (ValueError, RuntimeError) as exc:
                    st.error(str(exc))
        else:
            c1, c2, c3, c4 = st.columns(4)
            order_id = c1.text_input("New order ID", value="URG-001")
            product = c2.selectbox("Product", factory.products.product_id.tolist())
            quantity = int(c3.number_input("Quantity", 1, 1000, 8, 1))
            priority = int(c4.number_input("Priority (5 = highest)", 1, 5, 5, 1))
            due = int(st.number_input("Due minute", min_value=now, max_value=10_000_000, value=min(10_000_000, now + 1440), step=1))
            st.markdown('<div class="callout"><b>Urgent-order policy:</b> the order is released at the decision time. It bypasses the aggregate material planner; confirm raw-material availability separately.</div>', unsafe_allow_html=True)
            if st.button("Insert urgent order & re-optimize", type="primary"):
                try:
                    with st.spinner("Freezing history and inserting the urgent order…"):
                        revised_factory, result = reschedule_urgent_order(factory, base, now=now, order_id=order_id, product_id=product,
                                                                           quantity=quantity, due=due, priority=priority, time_limit=seconds)
                        record_run("Revised · urgent order", revised_factory, result)
                        st.session_state.revision = {"original": base_label, "revised": "Revised · urgent order"}
                except (ValueError, RuntimeError) as exc:
                    st.error(str(exc))
        revision = st.session_state.revision
        if revision and revision["original"] in st.session_state.runs and revision["revised"] in st.session_state.runs:
            before = st.session_state.runs[revision["original"]]; after = st.session_state.runs[revision["revised"]]
            result = after["result"]
            st.divider(); st.subheader(f"{revision['original']} → {revision['revised']}")
            status_note(result)
            if result.has_schedule:
                comp = compare_schedules(before["factory"], before["result"].schedule, after["factory"], result.schedule, result.history)
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Original makespan", f"{comp['original']['makespan']:,} min")
                c2.metric("Revised makespan", f"{comp['revised']['makespan']:,} min", delta=f"{comp['revised']['makespan']-comp['original']['makespan']:+,} min", delta_color="inverse")
                c3.metric("Newly late existing orders", comp["newly_late_orders"])
                c4.metric("Machine reassignments", comp["machine_reassignments"])
                st.caption(f"Aborted work: {comp['revised']['aborted_busy_minutes']} min. Stability objective = 10 × weighted tardiness + total absolute start shifts + 120 × machine reassignments. This is a trade-off, not a guarantee that every order stays on time.")
                t1, t2, t3, t4 = st.tabs(["Revised Gantt", "Original Gantt", "Order & operation changes", "Machine workload"])
                with t1:
                    st.plotly_chart(make_gantt(after["factory"], result.schedule, result.history), width="stretch", config={"displaylogo": False})
                    st.download_button("Download revised schedule CSV", csv_bytes(result.schedule), "revised_schedule.csv", "text/csv")
                    if not result.history.empty:
                        st.write("Discarded historical work")
                        st.dataframe(result.history[["operation_id", "machine_id", "start", "finish", "segment_type"]], hide_index=True, width="stretch")
                        st.download_button("Download aborted history CSV", csv_bytes(result.history), "aborted_history.csv", "text/csv")
                with t2:
                    st.plotly_chart(make_gantt(before["factory"], before["result"].schedule), width="stretch", config={"displaylogo": False})
                with t3:
                    st.write("Completion and tardiness by order")
                    st.dataframe(comp["orders"], hide_index=True, width="stretch")
                    st.write("Operation start and machine changes")
                    st.dataframe(comp["operations"], hide_index=True, width="stretch")
                with t4:
                    st.dataframe(comp["machines"], hide_index=True, width="stretch")
                    st.caption("Total busy minutes include any aborted historical work.")

elif page == "Schedule Comparison":
    heading("06 / schedule comparison", "Compare operational choices", "Compare dispatching rules and CP-SAT using measures calculated from their actual completion times.")
    if not st.session_state.runs:
        st.info("Generate schedules on the Scheduling page first.")
    else:
        rows = []
        for name, run in st.session_state.runs.items():
            result, factory = run["result"], run["factory"]
            row = {"schedule": name, "status": result.status, "orders": len(factory.orders), "units": int(factory.orders.quantity.sum()), "solve_seconds": round(result.solve_seconds, 2)}
            if result.has_schedule:
                summary = summary_metrics(factory, result.schedule, result.history)
                row.update({k: summary[k] for k in ("makespan", "total_tardiness", "weighted_tardiness", "late_orders", "scheduled_busy_minutes", "aborted_busy_minutes")})
            rows.append(row)
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        st.caption("Compare like-for-like scopes: a revised urgent order adds demand, and a capacity or breakdown scenario changes availability. FEASIBLE is not a proven optimum. No metric is guaranteed to improve.")
        st.markdown("**Choosing an objective.** A minimum-makespan plan prioritizes overall completion. A weighted-tardiness plan prioritizes due dates and priority; among equal weighted-tardiness solutions it minimizes makespan. Either may be preferable depending on the delivery commitment.")
        base_runs = {k: v for k, v in st.session_state.runs.items() if v["result"].has_schedule and not v["result"].metadata.get("scenario") and not k.startswith("Capacity")}
        if base_runs:
            with st.expander("Capacity what-if · extend a machine's daily shift"):
                st.caption("Before execution, extend one machine's end time on each of its working days, re-solve, and compare. Other constraints and demand are unchanged.")
                keys = list(base_runs)
                chosen = st.selectbox("Reference schedule", keys, index=len(keys)-1, key="capacity_base")
                base_run = base_runs[chosen]; factory = base_run["factory"]
                machines = factory.machines[factory.machines.shift_end_minute < 1440]
                if machines.empty:
                    st.info("No machine has a shift that can be extended before midnight.")
                else:
                    machine = st.selectbox("Machine to extend", machines.machine_id.tolist(), key="capacity_machine")
                    old_end = int(machines.set_index("machine_id").loc[machine, "shift_end_minute"])
                    new_end = int(st.number_input("New shift end (minute of day)", min_value=old_end+1, max_value=1440, value=min(1440, old_end+60), step=1))
                    c1, c2, c3 = st.columns(3)
                    rate = float(c1.number_input("Cost per added available hour", min_value=0.0, value=0.0, step=1.0))
                    delay_cost = float(c2.number_input("Cost per weighted tardy minute", min_value=0.0, value=0.0, step=1.0))
                    limit = c3.slider("What-if solve limit (seconds)", 3, 60, 8, 1)
                    objective = st.selectbox("What-if objective", ["makespan", "weighted_tardiness"])
                    st.caption("Cost estimate charges all added available hours over the horizon and values the change in weighted tardiness at your rate. It omits other costs/benefits.")
                    if st.button("Run capacity what-if", type="primary"):
                        try:
                            with st.spinner("Re-solving with the expanded shift…"):
                                expanded, extra = extend_machine_shift(factory, machine, new_end)
                                result = solve_schedule(expanded, objective, limit)
                                label = f"Capacity · {machine} to {new_end}"
                                record_run(label, expanded, result)
                                st.session_state.capacity_result = {"base": chosen, "label": label, "extra": extra, "rate": rate, "delay_cost": delay_cost}
                        except (ValueError, RuntimeError) as exc:
                            st.error(str(exc))
                cr = st.session_state.capacity_result
                if cr and cr["base"] in st.session_state.runs and cr["label"] in st.session_state.runs:
                    before = st.session_state.runs[cr["base"]]; after = st.session_state.runs[cr["label"]]
                    status_note(after["result"])
                    if after["result"].has_schedule:
                        estimate = cost_estimate(before["factory"], before["result"].schedule, after["factory"], after["result"].schedule, cr["extra"], cr["rate"], cr["delay_cost"])
                        st.dataframe(pd.DataFrame([estimate]), hide_index=True, width="stretch")
                        st.caption("This compares returned schedules; time-limited FEASIBLE runs do not prove the best achievable expansion benefit.")

elif page == "Model Configuration":
    heading("07 / model configuration", "Constraints & model assumptions", "Understand what the solver enforces, what its status means, and where the model boundary sits.")
    a, b = st.columns(2)
    with a:
        st.subheader("Enforced in CP-SAT")
        st.markdown("""- One eligible machine per operation; machine-specific processing and fixed setup.
- Exactly one non-preemptive setup-plus-processing interval per operation.
- Routing precedence, order release, machine no-overlap.
- Daily same-day shifts, weekdays, maintenance and simulated breakdowns.
- Completed and unaffected in-progress operations fixed during rescheduling.
- Interrupted work is recorded, discarded, and restarted after repair on the same machine.""")
    with b:
        st.subheader("Not modeled")
        st.markdown("""- Sequence-dependent setup, operator/tool constraints or overtime.
- Split batches, preemption, partial-operation credit or overlapping routing steps.
- Inventory balances, material arrival timing, raw material allocation for urgent orders.
- Demand uncertainty, stochastic breakdowns or a factory deployment.
- Cross-midnight shifts; represent only a single same-day shift per machine.""")
    st.subheader("Objectives")
    st.code("makespan:  minimize Cmax\nweighted tardiness:  minimize (H + 1) × Σ(priority × tardiness) + Cmax\nrescheduling:  minimize 10 × Σ(priority × tardiness) + Σ|new start − old start| + 120 × reassignments", language=None)
    st.caption("H is the scheduling horizon in minutes. The weighted-tardiness formula is lexicographic because 0 ≤ Cmax ≤ H. The rescheduling formula is a transparent weighted trade-off, not lexicographic.")
    st.subheader("Solver status")
    st.markdown("**OPTIMAL** proves the stated objective; **FEASIBLE** is a valid incumbent without proof; **INFEASIBLE** is a proof under the modeled horizon; **UNKNOWN** means no conclusion; **HEURISTIC_FAILED** only means a dispatch rule could not place all operations.")
    if st.session_state.runs:
        st.dataframe(pd.DataFrame([{"schedule": k, "status": v["result"].status, "objective": v["result"].objective,
                                    "objective_value": v["result"].objective_value, "best_bound": v["result"].best_bound,
                                    "solve_seconds": round(v["result"].solve_seconds, 2)} for k, v in st.session_state.runs.items()]), hide_index=True, width="stretch")
    st.caption("See docs/mathematical_formulation.md and docs/assumptions.md in the project for equations and input schema.")
