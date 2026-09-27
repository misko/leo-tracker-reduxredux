"""Check training isolation and exact propagation audits for joint fitting."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from run_joint import Objective, site

HERE = Path(__file__).resolve().parent


def synthetic_objective():
    center = [37.85, -122.48]
    receiver, up = site(*center)
    times = np.arange(8.)
    mask = np.array([True, False] * 4)
    position = np.broadcast_to(receiver + 550 * up, (2, 41, 8, 3)).copy()
    velocity = np.broadcast_to(np.array([1., 2., 3.]), position.shape).copy()
    position[1] += 20
    track = dict(track_id='a', receiver_id=0, y=times * 7, mask=mask,
                 centered_t=times-times[mask].mean())
    return Objective([track], {'a': (position, velocity, None)}, center, 2, [0])


def test_held_values_cannot_change_training_objective():
    model = synthetic_objective()
    x = np.array([.5, -.5, .125, 2.])
    before = model.evaluate(x, True)
    model.tracks[0]['y'][~model.tracks[0]['mask']] += 1e6
    after = model.evaluate(x, True)
    assert before['train'] == after['train']
    assert before['penalized_train'] == after['penalized_train']
    assert before['held'] != after['held']


@pytest.mark.parametrize('tau', [-5., -.125, 5.])
def test_zero_drift_matches_control_and_constant_exact_banks(tau):
    model = synthetic_objective()
    control = model.evaluate(np.array([0., 0., tau]), False)
    drift = model.evaluate(np.array([0., 0., tau, 0.]), True)
    exact = model.evaluate(np.array([0., 0., tau]), False, model.banks)
    for key in ['train', 'penalized_train', 'held']:
        assert control[key] == drift[key] == exact[key]


def test_completed_results_match_frozen_protocol():
    protocol_bytes = (HERE/'protocol.json').read_bytes()
    protocol = json.loads(protocol_bytes)
    assert hashlib.sha256((HERE/'run_joint.py').read_bytes()).hexdigest() == protocol['source_sha256']
    for name in protocol['inputs']:
        result = json.loads((HERE/name.replace('-plan', '')).read_text())
        assert result['complete']
        assert result['protocol_sha256'] == hashlib.sha256(protocol_bytes).hexdigest()
        assert result['input_sha256'] == protocol['inputs'][name]
        for arm in result['arms'].values():
            assert arm['best'] == max(arm['runs'], key=lambda r: r['penalized_train'])
            assert arm['maximum_interpolation_error_hz'] < 1.
            assert np.isfinite(arm['exact_held'])
