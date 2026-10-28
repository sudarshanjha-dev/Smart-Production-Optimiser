from src.dispatching_rules import dispatch_schedule
from src.gantt_chart import make_gantt
from src.schedule_metrics import order_metrics, summary_metrics, machine_workload
from src.calendars import machine_windows


def test_gantt_exactly_matches_schedule_and_idle_is_not_work(tiny_factory):
    r = dispatch_schedule(tiny_factory, 'FIFO')
    fig = make_gantt(tiny_factory, r.schedule)
    traces = [t for t in fig.data if t.meta['kind'] == 'operation']
    assert len(traces) == len(r.schedule)
    by_id = r.schedule.set_index('operation_id')
    for t in traces:
        row = by_id.loc[t.meta['operation_id']]
        assert t.base[0] == row.start
        assert t.x[0] == row.finish - row.start
        assert t.y[0] == row.machine_id
    # An order filter must not treat hidden-order work as idle.
    filtered = make_gantt(tiny_factory, r.schedule, orders=['J1'])
    for t in filtered.data:
        if t.meta['kind'] == 'idle':
            machine = t.meta['machine_id']
            for start, duration in zip(t.base, t.x):
                for row in r.schedule[r.schedule.machine_id == machine].itertuples():
                    assert not (start < row.finish and row.start < start + duration)
                assert any(a <= start and start + duration <= b for a, b in machine_windows(tiny_factory, machine))


def test_metrics_are_derived_from_finish_times(tiny_factory):
    r = dispatch_schedule(tiny_factory, 'FIFO')
    orders = order_metrics(tiny_factory, r.schedule)
    metrics = summary_metrics(tiny_factory, r.schedule)
    assert metrics['makespan'] == int(r.schedule.finish.max())
    assert metrics['weighted_tardiness'] == int((orders.tardiness_minutes * orders.priority).sum())
    assert metrics['late_orders'] == int((orders.completion_minute > orders.due_minute).sum())
    assert sum(machine_workload(tiny_factory, r.schedule).scheduled_busy_minutes) == int((r.schedule.finish-r.schedule.start).sum())
