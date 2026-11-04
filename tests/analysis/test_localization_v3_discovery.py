from copy import deepcopy

import numpy as np
import pytest

from leo.analysis.localization_v3.discovery import (
    coherent_phase,
    project_radio_state,
    signature,
    standard_problem,
    statistics,
)
from leo.analysis.localization_v3.position import NormalPosition
from tests.analysis.test_localization_v3_position import prepared
from tests.analysis.test_localization_v3_scan import example


def test_coherent_phase_does_not_average_separated_modes():
    phase, support, count = coherent_phase([0., .1, .2, 100.], [.1]*4, [1., 1., 1., 2.])
    assert phase == .1 and support == 3 and count == 3
    with pytest.raises(ValueError):
        coherent_phase([0.], [0.], [1.])


def test_seed_projection_preserves_inputs_and_enforces_receiver_contrast():
    _, _, _, state, _ = example()
    state['beta'][4:8] = [-99999., 99999., 99999., 99999.]
    before = state['beta'].copy()
    projected = project_radio_state(state)
    np.testing.assert_array_equal(state['beta'], before)
    rates = projected['beta'][4:8].reshape(2, 2) / 150
    assert np.all(abs(rates.mean(axis=1)) <= 30)
    assert np.all(abs(np.diff(rates, axis=1)) <= 3)


def test_discovery_stats_preserve_all_samples_but_mark_only_active_curvature():
    scan, _, _, _, base = example()
    groups = [(t['key'], [t]) for t in scan.tracks]
    stats = statistics(groups, dict(time_s=scan.times, doppler_0=base[0], elevation_deg=base[1]),
                       {'1':0., '2':0.})
    assert stats['active'].tolist() == [True, False, False]
    assert stats['count'].tolist() == [41, 21, 21]
    assert stats['visible'].all()
    assert (stats['rss'] == 0).all()


def test_signature_rejects_duplicate_fragments():
    scan, node = prepared()
    assert len(signature(node)) == len(scan.curved)
    changed = deepcopy(node)
    changed['seed']['rows'] *= 2
    changed['aliases'] *= 2
    with pytest.raises(ValueError, match='duplicate'):
        signature(changed)


def test_discovery_and_normal_likelihoods_keep_same_baseline_frequency_objective():
    scan, node = prepared()
    discovery = standard_problem(scan, node['seed'], 150., aliases=node['aliases'])
    normal = NormalPosition(scan, node, 150., False)
    point = np.array([.5, -.5])
    a, b = discovery.calculate(point), normal.calculate(point)
    for name in ('residual', 'coefficient', 'features', 'conditional_residual_hz'):
        np.testing.assert_array_equal(a[name], b[name])
    assert a['full_objective_offset'] == a['normalization_constant']-discovery.diagonal_logvolume
