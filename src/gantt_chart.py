"""Interactive Plotly Gantt generated exclusively from schedule rows."""
from __future__ import annotations
from datetime import timedelta
import pandas as pd
import plotly.graph_objects as go
from plotly.colors import qualitative
from .calendars import machine_windows, blocked_windows, subtract_intervals
from .data_loader import FactoryData


def _clock(factory: FactoryData, minute: int) -> str:
    return (factory.origin + timedelta(minutes=int(minute))).strftime("%d %b %Y %H:%M")


def make_gantt(factory: FactoryData, schedule: pd.DataFrame, history: pd.DataFrame | None = None,
               machines: list[str] | None = None, orders: list[str] | None = None,
               show_idle: bool = True, show_unavailable: bool = True) -> go.Figure:
    """Time axis is integer minutes; hover also includes factory-local timestamps.

    Filters hide rows, not occupancy: idle is always computed against the entire
    schedule (including aborted history), so filtered-out work is never called idle.
    Each actual operation trace carries its operation_id and exact start/duration.
    """
    history = history if history is not None else pd.DataFrame(columns=schedule.columns)
    machine_ids = [str(m) for m in factory.machines.machine_id if machines is None or m in machines]
    if schedule.empty:
        return go.Figure().update_layout(title="No schedule to display")
    max_end = max(int(schedule.finish.max()), int(history.finish.max()) if not history.empty else 0)
    shown = schedule[schedule.machine_id.isin(machine_ids)]
    if orders is not None:
        shown = shown[shown.order_id.isin(orders)]
    fig = go.Figure()
    if show_unavailable:
        for machine in machine_ids:
            spans = [(a, min(b, max_end)) for a, b in blocked_windows(factory, machine) if a < max_end]
            if spans:
                fig.add_trace(go.Bar(y=[machine] * len(spans), base=[a for a, b in spans],
                    x=[b - a for a, b in spans], orientation="h", width=0.72,
                    name="Unavailable", legendgroup="Unavailable", showlegend=machine == machine_ids[0],
                    marker=dict(color="#dde3e9", line=dict(width=0)), opacity=0.65,
                    hovertemplate="Unavailable / off shift<br>%{y}<br>Start: %{base} min<br>Duration: %{x} min<extra></extra>",
                    meta={"kind": "unavailable", "machine_id": machine}))
    if show_idle:
        for machine in machine_ids:
            occupied = [(int(x.start), int(x.finish)) for x in schedule.itertuples(index=False) if x.machine_id == machine]
            occupied += [(int(x.start), int(x.finish)) for x in history.itertuples(index=False) if x.machine_id == machine]
            free = [(a, min(b, max_end)) for a, b in machine_windows(factory, machine) if a < max_end]
            spans = subtract_intervals(free, occupied)
            if spans:
                fig.add_trace(go.Bar(y=[machine] * len(spans), base=[a for a, b in spans], x=[b-a for a, b in spans],
                    orientation="h", width=0.40, name="Available idle", legendgroup="idle", showlegend=machine == machine_ids[0],
                    marker=dict(color="#c5d4d2"), opacity=0.75,
                    hovertemplate="Available idle<br>%{y}<br>Start: %{base} min<br>Duration: %{x} min<extra></extra>",
                    meta={"kind": "idle", "machine_id": machine}))
    palette = qualitative.Plotly + qualitative.Safe + qualitative.Set2 + qualitative.Dark24
    all_orders = sorted(schedule.order_id.unique().tolist())
    colors = {order: palette[i % len(palette)] for i, order in enumerate(all_orders)}
    used = set()
    for row in shown.itertuples(index=False):
        details = [[row.order_id, row.operation_id, row.operation_name, int(row.operation_sequence),
                    int(row.quantity), _clock(factory, row.start), _clock(factory, row.finish),
                    int(row.start), int(row.finish), int(row.setup_minutes), int(row.processing_minutes), row.machine_id]]
        fig.add_trace(go.Bar(y=[row.machine_id], x=[int(row.finish - row.start)], base=[int(row.start)], orientation="h",
            width=0.62, name=row.order_id, legendgroup=row.order_id, showlegend=row.order_id not in used,
            marker=dict(color=colors[row.order_id], line=dict(color="white", width=0.6)),
            text=[f"{row.order_id} · {row.operation_sequence}"], textposition="inside", insidetextanchor="middle",
            customdata=details,
            hovertemplate=("<b>%{customdata[0]}</b> · %{customdata[2]}<br>Operation: %{customdata[1]} (seq %{customdata[3]})"
                           "<br>Machine: %{customdata[11]} · Quantity: %{customdata[4]}"
                           "<br>Start: %{customdata[5]} (%{customdata[7]} min)"
                           "<br>Finish: %{customdata[6]} (%{customdata[8]} min)"
                           "<br>Setup: %{customdata[9]} min · Processing: %{customdata[10]} min<extra></extra>"),
            meta={"kind": "operation", "operation_id": row.operation_id, "machine_id": row.machine_id}))
        used.add(row.order_id)
    hist = history[history.machine_id.isin(machine_ids)] if not history.empty else history
    if orders is not None and not hist.empty:
        hist = hist[hist.order_id.isin(orders)]
    for i, row in enumerate(hist.itertuples(index=False)):
        fig.add_trace(go.Bar(y=[row.machine_id], base=[int(row.start)], x=[int(row.finish-row.start)], orientation="h", width=0.62,
            name="Aborted work", legendgroup="aborted", showlegend=i == 0,
            marker=dict(color="#e39757", pattern=dict(shape="/"), line=dict(color="#a85522", width=1)),
            text=[f"{row.order_id} · aborted"], textposition="inside",
            hovertemplate=f"Aborted (discarded): {row.operation_id}<br>Start: {_clock(factory,row.start)}<br>Interrupted: {_clock(factory,row.finish)}<br>Elapsed: {int(row.finish-row.start)} min<extra></extra>",
            meta={"kind": "aborted", "operation_id": row.operation_id, "machine_id": row.machine_id}))
    names = factory.machines.set_index("machine_id").machine_name.to_dict()
    fig.update_layout(barmode="overlay", height=max(360, 95 * len(machine_ids) + 160),
        margin=dict(l=20, r=20, t=24, b=36), plot_bgcolor="white", paper_bgcolor="white",
        font=dict(family="Arial, sans-serif", color="#24344a", size=12),
        xaxis=dict(title=f"Minutes from {factory.origin:%d %b %Y 00:00} (factory local time)", range=[0, max_end * 1.02], gridcolor="#ebeff4", zeroline=False),
        yaxis=dict(title="", categoryorder="array", categoryarray=list(reversed(machine_ids)),
                   tickmode="array", tickvals=machine_ids, ticktext=[f"{m} · {names[m]}" for m in machine_ids], showgrid=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0, font=dict(size=10)),
        hovermode="closest")
    return fig
