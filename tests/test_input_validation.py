import pandas as pd
import pytest
from src.data_loader import COLUMNS, InputError, load_sample, make_factory
from src.schedule_validator import validate_schedule
from src.scheduling_model import ScheduleResult, solve_schedule


def test_sample_csv_roundtrip_is_compatible(tmp_path):
    factory = load_sample()
    for key in COLUMNS:
        getattr(factory, key).to_csv(tmp_path / f'{key}.csv', index=False)
    frames = {key: pd.read_csv(tmp_path / f'{key}.csv', dtype={'working_days': str} if key == 'machines' else None) for key in COLUMNS}
    loaded = make_factory(**frames)
    assert len(loaded.orders) == 24 and len(loaded.routings) == len(factory.routings)


def test_duplicate_order_and_invalid_priority_rejected(tiny_factory):
    dup = pd.concat([tiny_factory.orders, tiny_factory.orders.iloc[[0]]], ignore_index=True)
    with pytest.raises(InputError, match='unique'):
        tiny_factory.replace(orders=dup)
    bad = tiny_factory.orders.copy(); bad.loc[0, 'priority'] = 6
    with pytest.raises(InputError, match='priority'):
        tiny_factory.replace(orders=bad)


def test_cross_resource_alternatives_are_rejected(tiny_factory):
    route = pd.concat([tiny_factory.routings, pd.DataFrame([['P', 1, 'Cut', 'B', 1, 0]], columns=tiny_factory.routings.columns)], ignore_index=True)
    with pytest.raises(InputError, match='same resource group'):
        tiny_factory.replace(routings=route)


def test_sample_cp_sat_returns_and_validates_feasible_incumbent():
    factory = load_sample()
    result = solve_schedule(factory, objective='makespan', time_limit=5, workers=4)
    assert result.status in {'FEASIBLE', 'OPTIMAL'}
    assert len(result.schedule) == 92
    assert validate_schedule(factory, result.schedule) == []


def test_unknown_status_is_not_feasible():
    assert not ScheduleResult('UNKNOWN').has_schedule
    assert not ScheduleResult('INFEASIBLE').has_schedule


def test_exported_schedule_can_be_reloaded_and_validated(tiny_factory, tmp_path):
    result = solve_schedule(tiny_factory, time_limit=5, workers=1)
    path = tmp_path / "schedule.csv"
    result.schedule.to_csv(path, index=False)
    assert validate_schedule(tiny_factory, pd.read_csv(path)) == []
