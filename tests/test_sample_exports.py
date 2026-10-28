from pathlib import Path
import pandas as pd
import pytest
from src.capacity_analysis import extend_machine_shift
from src.data_loader import load_sample
from src.schedule_metrics import summary_metrics
from src.schedule_validator import validate_schedule

RESULTS = Path(__file__).resolve().parents[1] / 'results'


def test_bundled_full_demand_schedule_exports_are_feasible():
    factory = load_sample()
    for name in ('fifo.csv', 'edd.csv', 'spt.csv', 'cp_sat_makespan.csv', 'cp_sat_weighted_tardiness.csv'):
        if not (RESULTS / name).exists() and name.startswith('cp_sat_'):
            continue  # Time-limited solver may return UNKNOWN on another machine.
        schedule = pd.read_csv(RESULTS / name)
        assert validate_schedule(factory, schedule) == [], name
        assert summary_metrics(factory, schedule)['order_count'] == 24


def test_bundled_breakdown_and_urgent_schedule_exports():
    if not (RESULTS / 'breakdown_schedule.csv').exists() or not (RESULTS / 'urgent_order_schedule.csv').exists():
        pytest.skip('A time-limited rescheduling run returned no incumbent')
    factory = load_sample()
    downtime = pd.concat([factory.downtimes, pd.DataFrame([['M01', 700, 880, 'Simulated breakdown']], columns=factory.downtimes.columns)], ignore_index=True)
    broken_factory = factory.replace(downtimes=downtime)
    revised = pd.read_csv(RESULTS / 'breakdown_schedule.csv')
    history = pd.read_csv(RESULTS / 'breakdown_aborted_history.csv')
    assert validate_schedule(broken_factory, revised, history) == []
    original = pd.read_csv(RESULTS / 'edd.csv')
    old, new = original.set_index('operation_id'), revised.set_index('operation_id')
    frozen = original[(original.finish <= 700) | ((original.start < 700) & (original.finish > 700) & (original.machine_id != 'M01'))]
    for row in frozen.itertuples():
        for column in ('machine_id', 'start', 'finish'):
            assert old.loc[row.operation_id, column] == new.loc[row.operation_id, column]
    urgent = pd.DataFrame([['URG-001', 'P-A', 8, 700, 1600, 5]], columns=factory.orders.columns)
    urgent_factory = factory.replace(orders=pd.concat([factory.orders, urgent], ignore_index=True))
    assert validate_schedule(urgent_factory, pd.read_csv(RESULTS / 'urgent_order_schedule.csv')) == []


def test_bundled_capacity_scenario_schedule_is_feasible():
    if not (RESULTS / 'capacity_expansion_schedule.csv').exists():
        pytest.skip('A time-limited capacity run returned no incumbent')
    factory = load_sample()
    expanded, extra = extend_machine_shift(factory, 'M06', 1080)
    assert extra == 600
    assert validate_schedule(expanded, pd.read_csv(RESULTS / 'capacity_expansion_schedule.csv')) == []


def test_offline_html_contains_exact_exported_operation_bars():
    import json
    import re
    html = (RESULTS / 'sample_gantt.html').read_text(encoding='utf-8')
    assert not re.search(r'<script\b[^>]*\bsrc\s*=', html, flags=re.IGNORECASE)
    # Parse Plotly's final newPlot call (the embedded library also defines it).
    text = html[html.rfind('Plotly.newPlot(') + len('Plotly.newPlot('):].lstrip()
    decoder = json.JSONDecoder()
    _, offset = decoder.raw_decode(text)  # div ID
    text = text[offset:].lstrip()
    assert text.startswith(',')
    traces, _ = decoder.raw_decode(text[1:].lstrip())
    source = RESULTS / 'cp_sat_makespan.csv'
    if not source.exists(): source = RESULTS / 'edd.csv'  # Same fallback as run_sample.py.
    schedule = pd.read_csv(source).set_index('operation_id')
    bars = [t for t in traces if t.get('meta', {}).get('kind') == 'operation']
    assert len(bars) == len(schedule)
    for bar in bars:
        row = schedule.loc[bar['meta']['operation_id']]
        assert bar['base'][0] == row.start
        assert bar['x'][0] == row.finish - row.start
        assert bar['y'][0] == row.machine_id
