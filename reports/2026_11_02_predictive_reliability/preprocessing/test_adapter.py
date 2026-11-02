"""Synthetic leakage and normalization checks; no scientific fits."""
import copy
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('preprocessing_adapter', HERE / 'adapter.py')
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


def fixture():
    from dsx01_hierarchical_bound import hierarchical_bound
    tracks = [dict(observation_ids=['a', 'b', 'c'], values=np.array([20., 80., -10.]))]
    scan = SimpleNamespace(tracks=tracks, radio_sigma_hz=600., fixed_window_noise={'old': True})
    base = SimpleNamespace(members=[0], keep=np.ones(3, bool), labels=[7], alias=[1])
    def factory(s, node, keep, arm, reference, weights, means, multiplier, nu):
        p = SimpleNamespace(members=[0], keep=keep, labels=[7], alias=[1],
                            point_noise=np.full(3, s.radio_sigma_hz),
                            features=np.array([[1., 0.], [1., 2.], [1., 4.]]))
        # Like the real closure, read point_noise at calculation time.
        p.calculate = lambda: hierarchical_bound(s.tracks[0]['values'][keep],
            p.features[keep], p.point_noise[keep], np.zeros(keep.sum(), int), powers=weights)
        return p
    d = dict(scan=scan, keep=np.ones(3, bool), means=np.array([2.5]), powers=np.array([.2]),
             problems={'fitted_c': (base, np.array([9., 10.]))},
             entries=[{'old': True}], families=[object()], problem_factory=factory)
    return d, dict(selected={'full_data': True}, gap_selected={'full_data': True})


def build(d, train):
    dd, zz, receipt = adapter.prepare_context(d, {}, train)
    p = dd['problem_factory'](dd['scan'], {}, dd['keep'], 'c0', dd['means'],
                              dd['powers'], dd['means'], 1., None)
    return dd, p, receipt


def test_held_outcomes_and_saved_empirical_metadata_do_not_change_training_posterior():
    d, _ = fixture()
    train = np.array([True, False, True])
    dd, p, receipt = build(d, train)
    before = p.calculate()
    changed = copy.deepcopy(d)
    changed['scan'].tracks[0]['values'][1] = 1e12
    changed['scan'].radio_sigma_hz = 41.
    changed['scan'].fixed_window_noise = {'held_empirical': 1e20}
    changed['powers'][:] = .99
    _, q, receipt2 = build(changed, train)
    after = q.calculate()
    assert receipt == receipt2
    for key in ('negative_twice_elbo', 'coefficient', 'noise_precision'):
        np.testing.assert_allclose(before[key], after[key], rtol=0, atol=0)
    assert np.all(dd['powers'] == 1)
    assert np.all(p.point_noise == 150)
    assert d['scan'].radio_sigma_hz == 600
    assert d['scan'].fixed_window_noise == {'old': True}


def test_base_noise_override_uses_full_normalized_bound():
    from dsx01_hierarchical_bound import hierarchical_bound
    d, _ = fixture()
    train = np.array([True, False, True])
    _, p, _ = build(d, train)
    expected = hierarchical_bound(np.array([20., -10.]), p.features[train],
        np.full(2, 150.), np.zeros(2, int), powers=np.ones(1))
    assert p.calculate()['negative_twice_elbo'] == expected['negative_twice_elbo']
    alternate = hierarchical_bound(np.array([20., -10.]), p.features[train],
        np.full(2, 300.), np.zeros(2, int), powers=np.ones(1))
    assert alternate['negative_twice_elbo'] != expected['negative_twice_elbo']


def test_zero_reference_and_common_regional_start_do_not_use_saved_endpoint():
    d, z = fixture()
    dd, zz, _ = adapter.prepare_context(d, z, np.array([True, False, True]))
    starts = adapter.initial_conditions(dd)
    np.testing.assert_array_equal(starts['start'], [0., 0.])
    np.testing.assert_array_equal(starts['reference'], [0.])
    np.testing.assert_array_equal(dd['means'], [2.5])
    assert dd['entries'] == [] and dd['families'] == []
    assert 'selected' not in zz and 'gap_selected' not in zz
    assert 'selected' in z


def test_reject_changed_membership_aliases_and_invalid_mask():
    d, _ = fixture()
    train = np.array([True, False, True])
    with pytest.raises(ValueError):
        adapter.prepare_context(d, {}, np.array([1, 0, 1]))
    d['keep'][1] = False
    with pytest.raises(ValueError):
        adapter.prepare_context(d, {}, np.ones(3, bool))
    dd, _, _ = adapter.prepare_context(d, {}, train)
    with pytest.raises(ValueError):
        dd['problem_factory'](dd['scan'], {}, np.ones(3, bool), 'c0', d['means'],
                              dd['powers'], d['means'], 1., None)


def test_receiver_basis_is_restriction_of_fixed_global_design():
    from leo.analysis.research.retained_track_likelihood import projected_receiver_basis
    times = np.array([0., 17., 49., 113., 230., 300.])
    train = np.array([True, False, True, True, False, True])
    np.testing.assert_array_equal(projected_receiver_basis(times)[train],
                                  projected_receiver_basis(times[train]))
