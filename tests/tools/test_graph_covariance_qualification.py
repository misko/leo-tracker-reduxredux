"""Guard against recovery acceptance with lost evidence or mismatched controls."""

from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from audit_graph_covariance_families import gls_mean
from benchmark_graph_covariance import position_pass
from probe_high_channel_correlated_noise import calibrate, noise_diagnostics, position_trial


def test_physical_gls_mean_preserves_common_uncertainty_and_order():
    covariance = np.eye(6) * 4 + np.ones((6, 6)) * 25
    y = np.arange(6.) + 10
    design = np.ones((6, 1))
    result = gls_mean(y, covariance, design)
    assert result['mean_hz'][0] == pytest.approx(y.mean())
    assert result['sigma_hz'][0] == pytest.approx(np.sqrt(25 + 4/6))
    perm = [4, 1, 5, 0, 2, 3]
    permuted = gls_mean(y[perm], covariance[np.ix_(perm, perm)], design[perm])
    for key in result:
        np.testing.assert_allclose(result[key], permuted[key])


@pytest.mark.parametrize('times', [[], [1, 2, 3], [1, 1, 1, 1]])
def test_insufficient_residual_evidence_does_not_pass(times):
    assert not noise_diagnostics(np.zeros(len(times)), np.asarray(times))['noise_screen_pass']


def test_covariance_does_not_mix_receiver_calibration():
    p = SimpleNamespace(members=[0, 1], calculate=lambda x: {})
    scan = SimpleNamespace(tracks=[dict(receiver=rx, times=np.arange(10.)) for rx in (1, 2)])
    with pytest.raises(ValueError, match='one receiver'):
        calibrate(dict(problems={'c0': (p, np.zeros(2))}, scan=scan), [0, 1], [])


@pytest.mark.parametrize('policy', ['nominal', 'active'])
def test_position_trial_preserves_control_support_policy(monkeypatch, policy):
    import ds23_frequency_events
    class ReachedBuilder(Exception):
        pass
    def capture(*args, base_problem_factory, **kwargs):
        assert base_problem_factory.keywords['support_policy'] == policy
        raise ReachedBuilder
    monkeypatch.setattr(ds23_frequency_events, 'make_event_problem', capture)
    d = dict(means=np.zeros(1), scan=None, node=None, keep=None, powers=None,
             model=None, support_policy=policy)
    with pytest.raises(ReachedBuilder):
        position_trial(d, [], {})


def valid_pair():
    row = dict(gates={'tracks': [dict(compatible=True)]}, linear_gates=[dict(compatible=True)],
               target=dict(noise={'noise_screen_pass': True}, per_track_noise={'CH8': {'noise_screen_pass': True}}),
               target_min_elevation_deg=10., final_phase_change_s=.001,
               physical_target_checks=[dict(bias_hz=20., raw_RMS_after_bias_hz=120.)],
               proposed_associated_ids=[1, 2, 3])
    return {a: deepcopy(row) for a in ('c0', 'fitted_c')}


@pytest.mark.parametrize('failure', ['lost_point', 'old_track', 'new_track', 'nonconverged', 'invisible'])
def test_one_arm_failure_vetoes_recovery(failure):
    pair = valid_pair()
    old = {a: dict(proposed_associated_ids=[1, 2]) for a in pair}
    assert position_pass(pair, old)
    row = pair['fitted_c']
    if failure == 'lost_point': row['proposed_associated_ids'] = [1, 3]
    elif failure == 'old_track': row['gates']['tracks'][0]['compatible'] = False
    elif failure == 'new_track': row['target']['per_track_noise']['CH8']['noise_screen_pass'] = False
    elif failure == 'nonconverged': row['final_phase_change_s'] = .1
    else: row['target_min_elevation_deg'] = -1
    assert not position_pass(pair, old)
