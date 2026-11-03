"""Synthetic adapter checks; no archives, hardware or numerical fitting required."""
import json
from types import SimpleNamespace

import numpy as np
import pytest

import process_stage as module


def fixture(tmp_path, monkeypatch):
    raw = SimpleNamespace(numbers=np.array([3, 2, 1]),
        position=np.arange(36).reshape(3, 4, 3), velocity=np.zeros((3, 4, 3)),
        initial=np.r_[37., -122., np.zeros(7)], sources={'synthetic': 'fixture'},
        times=np.arange(30.), measured=np.arange(30.) + 100.,
        rf=np.full(30, 11e9), receiver=np.arange(30)%2, channel=np.ones(30),
        group=np.arange(30), margin=np.full(30, .5), original_rows=np.arange(30)*10)
    root = tmp_path/'fits/test'
    root.mkdir(parents=True)
    cal_path = root/'calibration.json'
    cal_path.write_text('{}')
    cal = SimpleNamespace(data=raw, path=cal_path,
        record={'rf_center_hz': 11e9, 'arms': {
            'fitted-c': {'coefficient': 17.}, 'zero-c': {'coefficient': 0.}}},
        receiver_baseline=lambda arm: np.full(30, 5.))
    monkeypatch.setattr(module, 'configure', lambda: SimpleNamespace(FullCalibration=lambda _: cal))
    monkeypatch.setattr(module, 'WORK', tmp_path)
    assoc = root/'associations/fitted-c.json'
    assoc.parent.mkdir()
    record = {'final': {'assignments': [
        {'row_index': i*10, 'catalog_number': 1+i%2} for i in reversed(range(5, 25))],
        'selected': [{'catalog_number': 2, 'offset_s': .2}, {'catalog_number': 1, 'offset_s': -.1}]}}
    assoc.write_text(json.dumps(record))
    return raw, assoc, record


def test_frozen_position_rows_bank_baseline_and_no_mutation(tmp_path, monkeypatch):
    raw, _, _ = fixture(tmp_path, monkeypatch)
    data, metadata = module.prepare('test')
    np.testing.assert_array_equal(data.original_rows, np.arange(5, 25)*10)
    np.testing.assert_array_equal(data.measured, np.arange(5, 25)+95.)
    np.testing.assert_array_equal(data.numbers, [1, 2])
    np.testing.assert_array_equal(data.position, raw.position[[2, 1]])
    np.testing.assert_array_equal(data.initial, [37., -122., 0., 0., 0., 0., -.1, .2])
    np.testing.assert_array_equal(raw.measured, np.arange(30)+100.)
    assert metadata['calibration_coefficient'] == {'fitted-c': 17., 'zero-c': 0.}


def test_duplicate_window_is_not_double_counted(tmp_path, monkeypatch):
    raw, _, _ = fixture(tmp_path, monkeypatch)
    raw.group[6] = raw.group[5]
    with pytest.raises(ValueError, match='one candidate per window'):
        module.prepare('test')


def test_duplicate_assignment_rejected(tmp_path, monkeypatch):
    _, path, record = fixture(tmp_path, monkeypatch)
    record['final']['assignments'].append(record['final']['assignments'][0])
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match='Duplicate assigned observation'):
        module.prepare('test')


def test_missing_owner_rejected(tmp_path, monkeypatch):
    _, path, record = fixture(tmp_path, monkeypatch)
    record['final']['assignments'][0]['catalog_number'] = 9
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match='owner missing'):
        module.prepare('test')
