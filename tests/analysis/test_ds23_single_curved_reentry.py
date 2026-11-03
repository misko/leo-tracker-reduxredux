from types import SimpleNamespace

import numpy as np

from probe_ds23_single_curved_reentry import configurations, predictive_track_data


def test_unsupported_receiver_covariance_is_shared_and_never_discarded():
    keep = np.array([True, True, False, False, False])
    features = np.array([[1., 0.], [1., 0.], [0., 1000.], [0., 1000.], [0., 1000.]])
    result = dict(coefficient=np.zeros(2), coefficient_prior_precision=np.ones(2),
                  noise_precision=np.ones(2), features=features)
    track = dict(key='new', times=np.array([1., 2., 3.]), values=np.zeros(3),
                 observation_ids=['a', 'b', 'c'], receiver=2, channel=1)
    p = SimpleNamespace(keep=keep, calculate=lambda _:result, noise_groups=np.array([0, 0, 1, 1, 1]),
                        point_noise=np.full(5, 10.), members=[0, 1], slices=[slice(0, 2), slice(2, 5)],
                        hardware=np.zeros((5, 2)), smooth=np.zeros((5, 0)), q=np.ones(5),
                        rows=[dict(candidate_index=0), dict(candidate_index=1)],
                        scan=SimpleNamespace(tracks=[None, track], curved=[1]))
    d = dict(entries=[], powers=np.ones(2))
    data = predictive_track_data(d, p, np.zeros(2), 1)
    np.testing.assert_allclose(data['radio_covariance'], np.ones((3, 3))*1e6)
    np.testing.assert_allclose(data['base_covariance']-data['fixed_calibration_covariance'], data['radio_covariance'])
    np.testing.assert_array_equal(p.keep, keep)
    np.testing.assert_array_equal(data['values'], track['values'])


def test_all_nonempty_whole_track_combinations_and_original_identity_control():
    def row(k, old, best):
        return dict(row_index=k, original=dict(candidate_index=old),
                    best=None if best is None else dict(candidate_index=best))
    selections = configurations(dict(targets=[row(0, 1, 1), row(1, 2, 3), row(2, 4, 4)]))
    assert len(selections) == 8
    assert sorted(len(r) for r in selections) == [1, 1, 1, 1, 2, 2, 2, 3]
    assert any(len(r) == 1 and r[0][0]['row_index'] == 1 and r[0][1]['candidate_index'] == 2
               for r in selections)
