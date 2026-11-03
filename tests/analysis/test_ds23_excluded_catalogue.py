import numpy as np
import pytest

from ds23_excluded_catalogue import gaussian_candidates, propose_aliases, apply_changes, orbit_frequency_modes
from leo.analysis.research.retained_track_likelihood import PERIOD
from leo.analysis.research.orbit_uncertainty import paired_frequency_modes
from types import SimpleNamespace


def test_batch_predictive_density_matches_direct_correlated_covariance():
    rng = np.random.default_rng(42)
    raw = rng.normal(size=(4, 7))
    modes = rng.normal(size=(4, 7, 4))
    a = rng.normal(size=(7, 3))
    covariance = np.eye(7)+a@a.T
    result = gaussian_candidates(raw, modes, covariance)
    for k in range(4):
        dense = covariance+modes[k]@modes[k].T
        expected = raw[k]@np.linalg.solve(dense, raw[k])+np.linalg.slogdet(dense)[1]+7*np.log(2*np.pi)
        assert result['cost'][k] == pytest.approx(expected, abs=1e-12)
    changed = gaussian_candidates(raw[::-1], modes[::-1], covariance)
    np.testing.assert_allclose(changed['cost'], result['cost'][::-1])


def test_candidate_aliases_preserve_curve_groups_and_full_pilot_period():
    observed = np.array([100., 110., -30., -40.])
    groups = np.array([0, 0, 1, 1])
    predicted = np.stack((observed+PERIOD, observed-2*PERIOD))
    aliases, raw = propose_aliases(observed, predicted, groups, np.eye(4))
    np.testing.assert_array_equal(aliases, [[1, 1], [-2, -2]])
    np.testing.assert_allclose(raw, 0., atol=1e-9)


def test_simultaneous_replacements_do_not_cascade_or_change_predictive_membership():
    node = dict(seed=dict(rows=[dict(candidate_index=j, candidate_norad=j+100) for j in (1, 2)]), aliases=[0, 0])
    entries = [dict(candidate_index=1, norad=101, alias=0, observation_ids=['held'])]
    choices = [dict(changes=[dict(kind='curve', index=0, original_index=1, candidate_index=2, norad=102, alias=1),
                            dict(kind='linear', index=0, original_index=1, candidate_index=2, norad=102, alias=1)]),
               dict(changes=[dict(kind='curve', index=1, original_index=2, candidate_index=3, norad=103, alias=-1)])]
    changed, predictive = apply_changes(node, entries, choices)
    assert [r['candidate_index'] for r in changed['seed']['rows']] == [2, 3]
    assert predictive[0]['candidate_index'] == 2
    assert predictive[0]['observation_ids'] == ['held']
    assert node['seed']['rows'][0]['candidate_index'] == 1
    with pytest.raises(ValueError, match='overlapping'):
        apply_changes(node, entries, [choices[0], choices[0]])


def test_batch_physical_modes_match_existing_paired_geometry():
    rng = np.random.default_rng(1)
    times = np.array([0., 1., 2.])
    bank = dict(time_s=np.arange(-5., 6.), position_km=rng.normal(size=(2, 11, 3))*50+np.array([7000., 0., 0.]),
                velocity_km_s=rng.normal(size=(2, 11, 3)))
    modes = dict(time_s=bank['time_s'], position_km=rng.normal(size=(6, 11, 3)), velocity_km_s=rng.normal(size=(6, 11, 3))*.01)
    phases = np.array([.1, -.2])
    got = orbit_frequency_modes(bank, modes, times, phases, (37., -122.))
    expected = paired_frequency_modes(bank, modes, np.tile(times, 2), np.repeat(np.arange(2), 3), phases, 37., -122.)
    np.testing.assert_allclose(got, expected.reshape(2, 3, 3), rtol=1e-12, atol=1e-12)


def test_held_block_keeps_training_radio_covariance_and_does_not_use_held_values():
    from screen_ds23_excluded_catalogue import block_data
    features = np.array([[1., 0.], [2., 0.], [1., 1.], [3., 2.]])
    train = np.array([1, 1, 0, 0], bool)
    values = np.array([2., 4., 10., 30.])
    gram = np.eye(2)+features[train].T@features[train]
    coefficient = np.linalg.solve(gram, features[train].T@values[train])
    tracks = [dict(values=values[:2], receiver=1, channel=1),
              dict(values=values[2:], receiver=2, channel=3)]
    p = SimpleNamespace(hardware=np.ones((4, 1)), smooth=np.empty((4, 0)),
        powers=np.ones(2), noise_groups=np.array([0, 0, 1, 1]), keep=train,
        rows=[dict(candidate_index=20), dict(candidate_index=10)], members=[0, 1],
        slices=[slice(0, 2), slice(2, 4)], scan=SimpleNamespace(tracks=tracks),
        flat_times=np.arange(4.), q=np.ones(4), point_noise=np.ones(4),
        calculate=lambda x: dict(features=features, coefficient=coefficient,
            coefficient_prior_precision=np.ones(2), noise_precision=np.ones(2)))
    a = block_data(p, np.zeros(2), np.ones(4, bool), 10)
    h = features[2:, :1]
    expected = h@np.linalg.inv(gram)[:1, :1]@h.T+2*np.eye(2)+300**2*np.ones((2, 2))
    np.testing.assert_allclose(a['covariance'], expected)
    tracks[1]['values'] = values[2:]+1000
    b = block_data(p, np.zeros(2), np.ones(4, bool), 10)
    np.testing.assert_array_equal(a['covariance'], b['covariance'])
    np.testing.assert_allclose(b['observed']-a['observed'], 1000)


def test_receiver_split_without_curved_support_is_rejected_without_dropping_predictive_data():
    from ds23_receiver_family_search import orphan_predictive_labels
    node = dict(seed=dict(rows=[dict(candidate_index=1, candidate_norad=101)]), aliases=[0])
    entries = [dict(candidate_index=1, norad=101, alias=0, observation_ids=['RX2-linear'])]
    change = dict(kind='curve', index=0, original_index=1, candidate_index=2, norad=102, alias=0)
    partial, predictive = apply_changes(node, entries, [dict(changes=[change])])
    assert orphan_predictive_labels(partial, predictive) == [1]
    assert predictive == entries
    assert node['seed']['rows'][0]['candidate_index'] == 1
    full, coherent = apply_changes(node, entries, [dict(changes=[change,
        dict(kind='linear', index=0, original_index=1, candidate_index=2, norad=102, alias=0)])])
    assert orphan_predictive_labels(full, coherent) == []
    assert coherent[0]['observation_ids'] == entries[0]['observation_ids']
