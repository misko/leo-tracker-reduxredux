import numpy as np
import pytest

from leo.analysis.localization_v3.event_position import (
    attach_event_predictive,
    event_design,
    event_profile,
    make_event_problem,
)
from leo.analysis.localization_v3.history_position import make_problem
from tests.analysis.test_localization_v3_position import prepared


def problem(events=()):
    scan, node = prepared()
    scan.previous_sources = {}
    scan.elements = {'99999': dict(provenance=dict(element_epoch_utc_ns=0))}
    args = (scan, node, np.ones(41, bool), 'c0', np.zeros(1), np.ones(1), np.zeros(1))
    model = dict(multiplier=1., nu=None)
    return args, model, make_event_problem(*args, model, events)


def test_event_columns_preserve_receiver_band_family_and_rf_scaling():
    events = [dict(kind=k, receiver=1, band=1, candidate_index=3, time_s=2., sigma_hz=10.)
              for k in ('receiver', 'receiver_RF', 'band', 'family')]
    design = event_design([1., 2., 3., 4.], [1, 1, 1, 2], [8, 4, 8, 8],
                           np.full(4, 23.e9), [3, 3, 2, 3], events)
    np.testing.assert_array_equal(design, [[0., 0., 0., 0.], [10., 20., 0., 20.],
                                          [10., 20., 10., 0.], [0., 0., 0., 20.]])
    assert event_design([0., 1.], 1, 1, 11.5e9, 0, []).shape == (2, 0)


def test_empty_event_path_is_exact_history_likelihood():
    args, model, p = problem()
    original = make_problem(*args, model['multiplier'], model['nu'])
    a, b = p.calculate(np.zeros(2)), original.calculate(np.zeros(2))
    assert a.keys() == b.keys()
    for key in a:
        np.testing.assert_equal(a[key], b[key])
    assert p.events == [] and p.event_start == len(a['coefficient'])
    assert attach_event_predictive(p, [], np.ones(1)) is p


def test_event_hardware_extension_is_local_and_predictive_points_do_not_recalibrate():
    event = dict(kind='receiver', receiver=1, time_s=150., sigma_hz=300.)
    args, _, p = problem([event])
    scan = args[0]
    x = np.zeros(2)
    base = p.calculate(x)
    state = p.state(x)
    t = scan.tracks[p.members[0]]
    expected = (t['times'] >= 150.) * base['event_amplitudes_hz'][0]
    np.testing.assert_allclose(p.scan.hardware(t, state['beta'])-
        scan.hardware(t, state['beta'][:8]), expected, atol=1e-10)
    assert p.scan is not scan and len(state['beta']) == 9
    entry = dict(track_index=1, component='linear', candidate_index=0, norad=99999,
                 alias=0, points=21, observation_ids=scan.tracks[1]['observation_ids'])
    attach_event_predictive(p, [entry], np.ones(1))
    joint = p.calculate(x)
    np.testing.assert_array_equal(joint['coefficient'], base['coefficient'])
    assert joint['negative_twice_elbo'] == (
        base['negative_twice_elbo']+joint['linear_predictive_objective'])


def test_profile_matches_dense_integrated_covariance():
    y, sigma = np.array([2., -1., 3., 2.]), np.array([1., 2., 1., 3.])
    design, groups = np.array([[0.], [1.], [2.], [3.]]), np.array([0, 0, 1, 1])
    result = event_profile(y, design, sigma, groups, prior_sigma_hz=.5)
    covariance = np.diag(sigma**2)+design@design.T+.25*(groups[:, None] == groups[None, :])
    expected = (y@np.linalg.solve(covariance, y)+np.linalg.slogdet(covariance)[1]
                -2*np.log(sigma).sum())
    assert result['cost'] == pytest.approx(expected, abs=1e-12)
