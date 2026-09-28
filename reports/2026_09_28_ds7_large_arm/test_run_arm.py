import copy
import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location('large_run_arm', Path(__file__).with_name('run_arm.py'))
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def batch():
    capture = dict(session_id='scan-a', visit_indices=[1, 3], sample_rate_hz=2500000, manifest_sha256='abc')
    rows = [dict(session_id='scan-a', visit_index=i, rate_hz=2500000, manifest_sha256='abc', shape=[300000, 2, 2], dtype='int16') for i in (1, 3)]
    return capture, rows


def test_batch_rejects_missing_duplicate_and_wrong_geometry():
    capture, rows = batch()
    assert runner.validate_batch(rows, capture) == rows
    for bad in (rows[:1], [rows[0], rows[0]], list(reversed(rows))):
        with pytest.raises(ValueError):
            runner.validate_batch(bad, capture)
    bad = copy.deepcopy(rows)
    bad[0]['shape'][0] -= 1
    with pytest.raises(ValueError, match='geometry'):
        runner.validate_batch(bad, capture)


def phase(rows):
    return [dict(type='ready', method='goal40mag', mode='isolated', consumer_core=0, receivers=2, rate_hz=2500000, jobs=2),
            *[dict(type='job', index=i, case_id=f"ds7-scan-a-v{r['visit_index']}", status='processed', receivers=[{'receiver': 0}, {'receiver': 1}]) for i,r in enumerate(rows)],
            dict(type='complete', complete=True, jobs=2, processed=2, dropped_queue_full=0, detector_failures=0)]


def encoded(records):
    return '\n'.join(json.dumps(r) for r in records).encode()


def test_phase_binds_every_result_to_input():
    _, rows = batch()
    records = phase(rows)
    got, _, _ = runner.validate_phase(encoded(records), rows)
    assert [job['context'] for job in got] == rows
    records[1]['case_id'] = 'ds7-wrong-v1'
    with pytest.raises(ValueError, match='identity'):
        runner.validate_phase(encoded(records), rows)


def test_phase_refuses_drop_or_incomplete_receipt():
    _, rows = batch()
    records = phase(rows)
    records[-1]['dropped_queue_full'] = 1
    with pytest.raises(ValueError, match='dropped'):
        runner.validate_phase(encoded(records), rows)
    with pytest.raises(ValueError, match='inventory'):
        runner.validate_phase(encoded(records[:-1]), rows)
