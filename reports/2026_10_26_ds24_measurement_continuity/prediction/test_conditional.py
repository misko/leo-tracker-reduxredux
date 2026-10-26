import numpy as np
from conditional import node_forecast, evaluate, split_indices


def fixture():
    covariance = np.diag([2., 3., 4., 5.]) + 9*np.ones((4, 4))
    geometry = dict(nodes=np.array([-.2, .3]), log_prior_weights=np.log(np.array([.4, .6])/9),
        frequency=np.array([[1., 2., 3., 4.], [1.1, 1.8, 3.2, 4.1]]),
        modes=np.array([[[1., .1], [.4, .3], [-.2, .6], [.8, -.3]],
                        [[.9, .2], [.5, .4], [-.1, .5], [.7, -.4]]]))
    return covariance, geometry, np.array([1.3, 1.8, 3.4, 3.9])


def test_gaussian_conditional_matches_dense_joint_and_keeps_cross_covariance():
    covariance, geometry, raw = fixture()
    value = node_forecast(raw[:2], covariance, geometry['frequency'], geometry['modes'],
                          [0, 1], [2, 3], np.array([0]), 10.)
    for i in range(2):
        full = covariance + geometry['modes'][i] @ geometry['modes'][i].T
        gain = full[2:, :2] @ np.linalg.inv(full[:2, :2])
        expected = geometry['frequency'][i, 2:] + gain @ (raw[:2]-geometry['frequency'][i, :2])
        assert np.allclose(value['mean'][i, 0], expected, atol=1e-13)
        assert np.allclose(value['covariance'][i], full[2:, 2:]-gain@full[:2, 2:], atol=1e-13)
        assert not np.allclose(value['covariance'][i], full[2:, 2:])


def test_held_redaction_leaves_all_forecast_and_train_posterior_values_unchanged():
    covariance, geometry, raw = fixture()
    # evaluate's physical branch accepts the declared three-mode model.
    geometry['modes'] = np.pad(geometry['modes'], ((0,0),(0,0),(0,1)))
    a = evaluate(raw, covariance, geometry, [0,1], [2,3], True, 10.)
    changed = raw.copy(); changed[2:] += 1000
    b = evaluate(changed, covariance, geometry, [0,1], [2,3], True, 10.)
    for key in ('prediction_mean','prediction_covariance','posterior_node_alias_mass','alias_probabilities','shape_mean'):
        assert np.array_equal(a[key], b[key])
    assert a['held_negative_twice_log_density'] != b['held_negative_twice_log_density']
    assert a['joint_conditional_identity_error'] < 1e-12


def test_between_node_covariance_is_retained():
    covariance, geometry, raw = fixture()
    a = evaluate(raw, covariance, geometry, [0,1], [2,3], False, 10.)
    node = node_forecast(raw[:2], covariance, geometry['frequency'], np.zeros((2,4,0)),
                         [0,1], [2,3], np.arange(-4,5), 10.)
    weights = a['posterior_node_alias_mass']
    mean = np.einsum('na,nai->i', weights, node['mean'])
    within = np.einsum('n,nij->ij', weights.sum(axis=1), node['covariance'])
    between = np.einsum('na,nai,naj->ij', weights, node['mean']-mean, node['mean']-mean)
    assert np.allclose(a['prediction_covariance'], within+between, atol=1e-12)
    assert np.trace(between) > 0


def test_split_is_chronological_metadata_only_and_complete():
    times = np.r_[np.arange(28.), 5.]
    ids = np.array([f'id{i:02}' for i in range(29)])
    folds = split_indices(times, ids)
    assert [len(folds[0][1]),len(folds[0][2])] == [14,15]
    assert np.array_equal(folds[0][1], folds[1][2])
    assert np.array_equal(folds[0][2], folds[1][1])
    assert set(np.r_[folds[0][1], folds[0][2]]) == set(range(29))
