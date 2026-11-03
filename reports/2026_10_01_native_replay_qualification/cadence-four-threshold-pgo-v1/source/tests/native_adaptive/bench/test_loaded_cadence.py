from pathlib import Path
import json
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]/'tools'))
from evaluate_loaded_cadence import evaluate, main


def schedule(durations=(295, 297, 298, 250)):
    return {'fixed_cadence_and_capacity_passed': True, 'scans': [
        {'scan': i, 'downstream_wall_s': duration,
         'downstream_finished_before_next_scan_ready': None if i == len(durations)-1 else True}
        for i, duration in enumerate(durations)]}


def test_loaded_margin_and_final_drain_are_separate():
    result = evaluate(schedule((295, 297, 298, 500)), 300)
    assert result['passed']
    assert [s['margin_s'] for s in result['loaded_intervals']] == [5, 3, 2]
    assert result['excluded_drain_scan'] == 3


def test_successful_finite_completion_cannot_mask_slow_loaded_job():
    assert not evaluate(schedule((302, 300.6, 257)), 300, 2)['passed']
    assert not evaluate(schedule((299, 300, 299, 1)), 300)['passed']


def test_fast_durations_cannot_mask_waiting_for_previous_job():
    value = schedule()
    value['scans'][1]['downstream_finished_before_next_scan_ready'] = False
    assert not evaluate(value, 300)['passed']


def test_insufficient_loaded_intervals_fail():
    result = evaluate(schedule((1, 1)), 300)
    assert not result['passed'] and not result['sufficient_loaded_intervals']


@pytest.mark.parametrize('fault', ['unverified', 'nan', 'inventory', 'drain'])
def test_invalid_evidence_rejected(fault):
    value = schedule()
    if fault == 'unverified': value['fixed_cadence_and_capacity_passed'] = False
    elif fault == 'nan': value['scans'][0]['downstream_wall_s'] = float('nan')
    elif fault == 'inventory': value['scans'].pop(1)
    else: value['scans'][-1]['downstream_finished_before_next_scan_ready'] = True
    with pytest.raises(ValueError): evaluate(value, 300)


@pytest.mark.parametrize('science_passed', [False, True])
def test_cli_requires_science_and_preserves_existing_receipt(tmp_path, monkeypatch, science_passed):
    (tmp_path/'protocol.json').write_text(json.dumps({'period_ms': 300000}))
    (tmp_path/'evaluation.json').write_text(json.dumps({
        'passed': science_passed, 'schedule': schedule()}))
    monkeypatch.setattr(sys, 'argv', ['evaluate_loaded_cadence', str(tmp_path)])
    assert main() == (0 if science_passed else 2)
    output = tmp_path/'loaded-cadence-evaluation.json'
    before = output.read_bytes()
    assert json.loads(before)['passed'] is science_passed
    with pytest.raises(FileExistsError): main()
    assert output.read_bytes() == before
