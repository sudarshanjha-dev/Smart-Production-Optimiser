"""Plot the returned textile schedule, preserving source overnight boundaries."""
from __future__ import annotations
import plotly.graph_objects as go
from plotly.colors import qualitative
from .textile_data import INPUT_SHA256, TextileInstance, source_slot_label
from .textile_validation import validate_textile_schedule


def textile_gantt(instance: TextileInstance, schedule):
    errors = validate_textile_schedule(instance, schedule)
    if errors: raise ValueError("Cannot plot an invalid textile schedule")
    published = instance.input_hash == INPUT_SHA256
    palette = qualitative.Plotly
    tasks = sorted(schedule.task.unique())
    colors = {task: palette[i % len(palette)] for i, task in enumerate(tasks)}
    fig = go.Figure()
    for task in tasks:
        rows = schedule[schedule.task == task].sort_values('start_slot')
        base, labels = [], []
        for row in rows.itertuples(index=False):
            if published:
                # 07:00–23:00 source day, then 8h overnight. A task is never
                # allowed to cross the compressed boundary.
                base.append((int(row.start_slot) * 5 + (int(row.start_slot) // 192) * 480) / 60)
                start, end = source_slot_label(int(row.start_slot)), source_slot_label(int(row.end_slot), end=True)
            else:
                base.append(int(row.start_slot)); start = f"slot {row.start_slot}"; end = f"slot {row.end_slot}"
            labels.append([row.operation_id, row.product, row.unit_id, row.mode_id, start, end, row.duration_minutes])
        lengths = (rows.duration_minutes / 60 if published else rows.duration_slots).tolist()
        fig.add_trace(go.Bar(name=task, x=lengths, y=rows.machine_id, base=base, orientation='h',
                             marker_color=colors[task], customdata=labels,
                             hovertemplate="<b>%{customdata[1]}</b> · %{customdata[2]}<br>"
                                "Task: " + task + "<br>Mode: %{customdata[3]}<br>"
                                "%{customdata[4]} → %{customdata[5]}<br>Duration: %{customdata[6]} min"
                                "<br>%{customdata[0]}<extra></extra>"))
    fig.update_layout(barmode='overlay', height=390, margin=dict(l=10,r=20,t=25,b=50),
                      plot_bgcolor='#fbfdfc', paper_bgcolor='rgba(0,0,0,0)',
                      legend=dict(orientation='h',yanchor='bottom',y=1.03,x=0),
                      xaxis=dict(title='Elapsed calendar time from Monday 07:00' if published else 'Working slot (5 min)',
                                 showgrid=True, gridcolor='#e7efec'),
                      yaxis=dict(title='', categoryorder='array', categoryarray=list(reversed(instance.machines))))
    if published:
        fig.update_xaxes(tickmode='array', tickvals=[24*i for i in range(6)],
                         ticktext=[f'{day} 07:00' for day in ('Mon','Tue','Wed','Thu','Fri','Sat')])
        for day in range(5):
            fig.add_vrect(x0=24*day+16, x1=24*(day+1), fillcolor='#e1eae6', opacity=0.38,
                          line_width=0, layer='below')
    return fig
