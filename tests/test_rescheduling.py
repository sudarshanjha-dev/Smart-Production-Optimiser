from src.dispatching_rules import dispatch_schedule
from src.rescheduling import reschedule_breakdown, reschedule_urgent_order
from src.schedule_validator import validate_schedule
from src.schedule_metrics import compare_schedules


def test_breakdown_aborts_and_restarts_full_operation(tiny_factory):
    original = dispatch_schedule(tiny_factory, 'FIFO').schedule
    running = original[(original.machine_id == 'A') & (original.start == 0)].iloc[0]
    # Cut lasts two minutes, so a failure at t=1 interrupts it.
    f2, r = reschedule_breakdown(tiny_factory, original, 'A', 1, 4, time_limit=5, workers=1)
    assert r.status == 'OPTIMAL'
    assert r.metadata['interrupted_operation_ids'] == [running.operation_id]
    assert len(r.history) == 1
    assert (int(r.history.iloc[0].start), int(r.history.iloc[0].finish)) == (0, 1)
    restarted = r.schedule.set_index('operation_id').loc[running.operation_id]
    assert restarted.machine_id == 'A' and restarted.start >= 4
    assert restarted.finish - restarted.start == 2  # full setup + work restarted
    assert validate_schedule(f2, r.schedule, r.history) == []


def test_completed_and_running_operations_are_frozen_for_urgent_order(tiny_factory):
    original = dispatch_schedule(tiny_factory, 'FIFO').schedule
    now = 3
    frozen = original[(original.finish <= now) | ((original.start < now) & (original.finish > now))]
    assert len(frozen) >= 2
    f2, r = reschedule_urgent_order(tiny_factory, original, now=now, order_id='URG', product_id='P', quantity=1, due=15, priority=5, time_limit=5, workers=1)
    assert r.status == 'OPTIMAL'
    new = r.schedule.set_index('operation_id')
    for row in frozen.itertuples():
        assert (new.loc[row.operation_id, 'start'], new.loc[row.operation_id, 'finish'], new.loc[row.operation_id, 'machine_id']) == (row.start, row.finish, row.machine_id)
    assert (r.schedule[r.schedule.order_id == 'URG'].start >= now).all()
    assert validate_schedule(f2, r.schedule) == []
    comparison = compare_schedules(tiny_factory, original, f2, r.schedule)
    assert comparison['orders'].new_order.sum() == 1
    assert comparison['original']['makespan'] == original.finish.max()
    assert comparison['revised']['makespan'] == r.schedule.finish.max()


def test_breakdown_freezes_completed_and_other_running_work(tiny_factory):
    original = dispatch_schedule(tiny_factory, 'FIFO').schedule
    now = 3
    original_index = original.set_index('operation_id')
    # At t=3 J1's cut is complete and J1's pack is running; J2's cut on A is interrupted.
    f2, result = reschedule_breakdown(tiny_factory, original, 'A', now, 5, time_limit=5, workers=1)
    assert result.status == 'OPTIMAL'
    revised = result.schedule.set_index('operation_id')
    for oid in ('J1::01', 'J1::02'):
        for column in ('start', 'finish', 'machine_id'):
            assert revised.loc[oid, column] == original_index.loc[oid, column]
    assert result.metadata['interrupted_operation_ids'] == ['J2::01']
    assert revised.loc['J2::01', 'start'] >= 5
    assert validate_schedule(f2, result.schedule, result.history) == []


def test_breakdown_can_be_proven_infeasible(tiny_factory):
    f = tiny_factory.replace(horizon=8)
    original = dispatch_schedule(f, 'FIFO').schedule
    f2, result = reschedule_breakdown(f, original, 'A', 1, 8, time_limit=5, workers=1)
    assert result.status == 'INFEASIBLE'
    assert not result.has_schedule
