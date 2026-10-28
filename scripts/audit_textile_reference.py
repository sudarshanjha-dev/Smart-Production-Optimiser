"""Audit the public output JSON and statistics workbook without treating them as an optimum.

From the repository root: python scripts/audit_textile_reference.py
The two reference files are fetched into a temporary directory and checksummed.
Or pass --reference-dir /path/to/downloads to use previously downloaded files.
No additional XLSX library is needed; this reads the relevant worksheet XML.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from hashlib import md5
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.request import Request, urlopen
from zipfile import ZipFile
import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.textile_data import load_published_bytes, parse_textile_json

FILES = {
    'Output_JSON_Schedule_Optimization.json': ('85c29dee9e1aa8bcd57df0d9b0e5de38', 386320),
    'Output_Statistics_Schedule_Optimization.xlsx': ('5edaa3399f34810c393581dfd70987b9', 967842),
}
NS = {'x': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def get_file(directory: Path, name: str) -> Path:
    path = directory / name
    if not path.exists():
        url = f'https://zenodo.org/records/4106746/files/{name}?download=1'
        with urlopen(Request(url, headers={'User-Agent':'SmartProductionOptimiser/1.0'}), timeout=45) as response:
            path.write_bytes(response.read(2_000_001))
    data = path.read_bytes(); checksum, size = FILES[name]
    if len(data) != size or md5(data).hexdigest() != checksum:
        raise ValueError(f'Published reference checksum/size mismatch: {name}')
    return path


def workbook_rows(path: Path) -> list[dict]:
    """Read columns A–E of the pinned workbook's Schedule Tables worksheet."""
    with ZipFile(path) as z:
        shared = ET.fromstring(z.read('xl/sharedStrings.xml'))
        strings = [''.join(si.itertext()) for si in shared.findall('x:si', NS)]
        sheet = ET.fromstring(z.read('xl/worksheets/sheet2.xml'))
        rows = []
        for row in sheet.findall('x:sheetData/x:row', NS):
            if int(row.attrib['r']) < 2: continue
            cells = {}
            for c in row.findall('x:c', NS):
                column = re.match(r'[A-Z]+', c.attrib['r']).group(0)
                if column not in 'ABCDE' or len(column) != 1: continue
                value = c.find('x:v', NS)
                if value is None: continue
                text = value.text
                cells[column] = strings[int(text)] if c.attrib.get('t') == 's' else float(text)
            if not all(c in cells for c in 'ABCDE'): continue
            task_id, unit = str(cells['B']), str(cells['E'])
            rows.append({'machine': str(cells['A']), 'task': re.sub(r'^T\d+- ', '', task_id).rsplit(' (',1)[0],
                         'start': int(cells['C']), 'end': int(cells['C'] + cells['D']),
                         'duration': int(cells['D']), 'product': re.sub(r'^P\d+- ', '', unit),
                         'unit': unit, 'task_id': task_id})
    return rows


def audit(directory: Path) -> dict:
    output_path = get_file(directory, 'Output_JSON_Schedule_Optimization.json')
    stats_path = get_file(directory, 'Output_Statistics_Schedule_Optimization.xlsx')
    reference = json.loads(output_path.read_text(encoding='utf-8'))
    instance = parse_textile_json(load_published_bytes()[0])
    rows = workbook_rows(stats_path)
    output_modes = {assignment['task_mode'] for cell in reference['cell_schedules']
                    for machine in cell['machines'] for assignment in machine['assignments']}
    unmatched_modes = sorted(output_modes - instance.modes.keys())
    machine_energy = {e['machineId']: e['energy'] for e in reference['statistics']['energyPerTimeFrameMachine']}
    nonmatching = []
    for row in rows:
        matches = [mode for mode in instance.task_modes[row['task']]
                   if mode in instance.machine_modes[row['machine']]
                   and instance.modes[mode].duration == row['duration']
                   and list(instance.modes[mode].power) == machine_energy[row['machine']][row['start']:row['end']]]
        if len(matches) != 1: nonmatching.append(row['task_id'])
    score = sum(max(0, sum(series[t] for series in machine_energy.values()) - instance.solar_availability[t])
                * instance.grid_prices[t] for t in range(instance.horizon))
    by_unit = defaultdict(list)
    for row in rows: by_unit[row['unit']].append(row)
    overlaps = []
    for unit, tasks in by_unit.items():
        for i, a in enumerate(tasks):
            for b in tasks[i+1:]:
                if a['start'] < b['end'] and b['start'] < a['end']:
                    overlaps.append({'unit': unit, 'tasks': [a['task_id'], b['task_id']],
                                     'intervals': [[a['start'],a['end']], [b['start'],b['end']]]})
    roks = []
    for unit, tasks in by_unit.items():
        if tasks[0]['product'] == 'ROK ELASTIC':
            one = [x for x in tasks if x['task'] == 'Harden[1.5]']
            two = [x for x in tasks if x['task'] == 'Harden[2]']
            if one and two: roks.append({'unit':unit, 'json_order_holds':max(x['end'] for x in one) <= min(x['start'] for x in two),
                                         'paper_order_holds':max(x['end'] for x in two) <= min(x['start'] for x in one)})
    repeated_product = [p for p, n in Counter(r['product'] for r in instance.requests).items() if n > 1]
    return {'workbook_rows':len(rows), 'workbook_product_unit_ids':len(by_unit),
            'output_mode_ids_absent_from_input':unmatched_modes,
            'workbook_rows_without_unique_matching_input_profile':len(nonmatching),
            'recorded_cost_score':reference['statistics']['cost'], 'recomputed_cost_score':score,
            'same_unit_overlaps':overlaps, 'ROK_order_observed':roks,
            'products_with_multiple_input_request_rows':repeated_product,
            'note':'Reference JSON uses different mode identifiers; workbook product IDs do not unambiguously map to original duplicate request rows. Never treat the published score as a comparable optimum.'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--reference-dir', type=Path, help='Directory containing the two original reference files')
    args = parser.parse_args()
    if args.reference_dir:
        print(json.dumps(audit(args.reference_dir), indent=2))
    else:
        with TemporaryDirectory() as tmp:
            print(json.dumps(audit(Path(tmp)), indent=2))

if __name__ == '__main__': main()
