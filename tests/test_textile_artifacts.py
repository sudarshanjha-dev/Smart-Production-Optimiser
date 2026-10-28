import json
from pathlib import Path
from zipfile import ZipFile
import pandas as pd
from scripts.audit_textile_reference import workbook_rows
from src.textile_data import load_published_bytes, parse_textile_json
from src.textile_metrics import textile_metrics
from src.textile_validation import validate_textile_schedule

ROOT = Path(__file__).resolve().parents[1]


def test_persisted_benchmarks_revalidate_and_recompute():
    blob, _ = load_published_bytes()
    for folder in ('textile', 'textile_profile'):
        directory = ROOT / 'results' / folder
        recorded = json.loads((directory / 'benchmark.json').read_text())
        instance = parse_textile_json(blob, recorded['order_interpretation'], unit_exclusive=recorded['unit_exclusive'])
        for name in ('baseline', 'optimized'):
            schedule = pd.read_csv(directory / f'{name}.csv')
            assert not validate_textile_schedule(instance, schedule, makespan_limit=recorded['makespan_limit'])
            actual = textile_metrics(instance, schedule)
            key = 'baseline' if name == 'baseline' else 'solver'
            assert actual['makespan_slots'] == recorded[key]['metrics']['makespan_slots']
            assert abs(actual['source_style_cost_score'] - recorded[key]['metrics']['source_style_cost_score']) < 1e-9
        assert recorded['comparison_valid_under_same_constraints']


def test_workbook_reader_without_openpyxl(tmp_path):
    xlsx = tmp_path / 'minimal.xlsx'
    ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    strings = ['Machine Id','Task Id','Start','Duration','Product Id','M1','T1- X (M1)','P1- P']
    shared = f'<sst xmlns="{ns}">' + ''.join(f'<si><t>{s}</t></si>' for s in strings) + '</sst>'
    sheet = f'''<worksheet xmlns="{ns}"><sheetData>
    <row r="1"><c r="A1" t="s"><v>0</v></c></row>
    <row r="2"><c r="A2" t="s"><v>5</v></c><c r="B2" t="s"><v>6</v></c>
    <c r="C2"><v>3</v></c><c r="D2"><v>2</v></c><c r="E2" t="s"><v>7</v></c></row>
    </sheetData></worksheet>'''
    with ZipFile(xlsx, 'w') as z:
        z.writestr('xl/sharedStrings.xml',shared)
        z.writestr('xl/worksheets/sheet2.xml',sheet)
    rows = workbook_rows(xlsx)
    assert rows[0]['task'] == 'X' and rows[0]['start'] == 3 and rows[0]['end'] == 5
    assert rows[0]['unit'] == 'P1- P'


def test_published_gantt_uses_calendar_not_compressed_axis():
    from src.textile_gantt import textile_gantt
    blob, _ = load_published_bytes()
    instance = parse_textile_json(blob)
    schedule = pd.read_csv(ROOT / 'results' / 'textile' / 'optimized.csv')
    fig = textile_gantt(instance, schedule)
    assert len(fig.data) == schedule.task.nunique()
    for trace in fig.data:
        rows = schedule[schedule.task == trace.name].sort_values('start_slot')
        for base, start in zip(trace.base, rows.start_slot):
            assert base == (int(start)*5 + (int(start)//192)*480)/60
