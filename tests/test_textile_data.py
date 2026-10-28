import copy
import json
import pytest
from src.textile_data import (INPUT_SHA256, TextileInputError, load_published_bytes,
                              parse_textile_json, source_slot_label)
from src.textile_dispatching import dispatch_textile
from src.textile_validation import validate_textile_schedule


def test_published_dataset_counts_and_both_order_interpretations():
    blob, provenance = load_published_bytes()
    json_order = parse_textile_json(blob, 'json')
    paper_order = parse_textile_json(blob, 'paper')
    assert json_order.input_hash == INPUT_SHA256
    assert (json_order.total_units, len(json_order.operations), len(json_order.machines), len(json_order.products)) == (132, 275, 3, 14)
    assert json_order.time_leaps == (192, 384, 576, 768, 960)
    assert json_order.order_pairs == (('Harden[1.5]', 'Harden[2]'),)
    assert paper_order.order_pairs == (('Harden[2]', 'Harden[1.5]'),)
    assert len([x for x in json_order.operations if x.deadline is not None]) == 4
    assert any('Harden[1] TM2' in w for w in json_order.warnings)
    assert source_slot_label(192, end=True) == 'Mon 23:00'
    assert source_slot_label(192) == 'Tue 07:00'


def test_small_case_expands_runs_and_uses_explicit_order(textile_fixture):
    p = parse_textile_json(json.dumps(textile_fixture))
    r = dispatch_textile(p)
    assert r.status == 'HEURISTIC' and validate_textile_schedule(p, r.schedule) == []
    x, y = (r.schedule.set_index('task').loc[t] for t in ('X','Y'))
    assert x.end_slot <= y.start_slot
    assert r.schedule.end_slot.max() == 4
    opposite = parse_textile_json(json.dumps(textile_fixture), 'paper')
    r2 = dispatch_textile(opposite)
    x, y = (r2.schedule.set_index('task').loc[t] for t in ('X','Y'))
    assert y.end_slot <= x.start_slot
    assert validate_textile_schedule(opposite, r2.schedule) == []


def test_adapter_rejects_malformed_and_unsupported_fields(textile_fixture):
    with pytest.raises(TextileInputError, match='Invalid UTF-8 / JSON'):
        parse_textile_json('{not json')
    bad = copy.deepcopy(textile_fixture); del bad['products']
    with pytest.raises(TextileInputError, match='missing required fields'):
        parse_textile_json(json.dumps(bad))
    bad = copy.deepcopy(textile_fixture); bad['constraints'][0]['type'] = 'Unimplemented'
    with pytest.raises(TextileInputError, match='unsupported source constraint'):
        parse_textile_json(json.dumps(bad))
    bad = copy.deepcopy(textile_fixture); bad['task_modes'][0]['power'] = []
    with pytest.raises(TextileInputError, match='power'):
        parse_textile_json(json.dumps(bad))
    bad = copy.deepcopy(textile_fixture); bad['machines'][0]['task_modes'] = ['absent']
    with pytest.raises(TextileInputError, match='unknown mode'):
        parse_textile_json(json.dumps(bad))
    bad = copy.deepcopy(textile_fixture); bad['energy_sources'][0]['price'] = [0.1]
    with pytest.raises(TextileInputError, match='exactly 10'):
        parse_textile_json(json.dumps(bad))


def test_missing_bundled_data_uses_download_fallback(monkeypatch):
    import src.textile_data as data
    original, _ = data.load_published_bytes()
    monkeypatch.setattr(data, 'BUNDLED_INPUT', data.BUNDLED_INPUT.parent / 'does-not-exist.json')
    monkeypatch.setattr(data, 'download_published_input', lambda: original)
    blob, provenance = data.load_published_bytes()
    assert blob == original and 'Zenodo download' in provenance


def test_published_baseline_validates_against_all_constraints():
    blob, _ = load_published_bytes()
    for interpretation in ('json', 'paper'):
        p = parse_textile_json(blob, interpretation)
        baseline = dispatch_textile(p)
        assert baseline.status == 'HEURISTIC'
        assert len(baseline.schedule) == 275
        assert validate_textile_schedule(p, baseline.schedule) == []
        assert baseline.schedule.end_slot.max() <= p.horizon


def test_verified_remote_download_is_cached_and_checked(monkeypatch):
    import src.textile_data as data
    blob, _ = data.load_published_bytes()
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, count): return blob
    calls = []
    def fake_open(request, timeout):
        calls.append(request.full_url)
        return Response()
    data.download_published_input.cache_clear()
    monkeypatch.setattr(data, 'urlopen', fake_open)
    assert data.download_published_input() == blob
    assert data.download_published_input() == blob and len(calls) == 1
    data.download_published_input.cache_clear()
    class BadResponse(Response):
        def read(self, count): return b'wrong contents'
    monkeypatch.setattr(data, 'urlopen', lambda *a, **k: BadResponse())
    with pytest.raises(TextileInputError, match='SHA-256'):
        data.download_published_input()
    data.download_published_input.cache_clear()


def test_duplicate_json_keys_are_rejected():
    with pytest.raises(TextileInputError, match='Duplicate JSON key'):
        parse_textile_json('{"cells":[], "cells":[]}')
