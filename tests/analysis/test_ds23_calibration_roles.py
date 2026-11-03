from types import SimpleNamespace
import numpy as np
import pytest

from ds23_calibration_roles import predictive_roles


def fixture(power=.2):
    track = dict(key='source', times=np.array([0., 10., 20.]), values=np.array([1., 2., 3.]),
        observation_ids=['a', 'b', 'c'], receiver=1, channel=1, rf_hz=11.5e9)
    other = dict(track, key='anchor', observation_ids=['d', 'e', 'f'])
    scan = SimpleNamespace(tracks=[track, other], rx_basis=[np.zeros((3, 1))]*2,
        white=[None]*2, index=[np.arange(3)]*2, radio_sigma_hz=40.,
        fixed_window_noise=dict(extra_parameter_BIC_gain=-1,
            per_observation_noise_sigma_hz={x:99. for x in 'abcdef'}))
    rows = [dict(component=t['key'], candidate_index=0, candidate_norad=123) for t in scan.tracks]
    data = dict(scan=scan, observations=[dict(observation_id=x) for x in 'abcdef'],
        keep=np.array([True, False, True, True, True, True]), entries=[],
        powers=np.array([power, 1.]), node=dict(aliases=[2, 0]),
        base=SimpleNamespace(rows=rows, members=[0, 1], slices=[slice(0, 3), slice(3, 6)]))
    inventory = dict(rows=[dict(row=0, component='source', observation_ids=['a', 'c'],
        would_retain_calibration=False)])
    return data, inventory


def test_exact_partial_mask_and_alias_retained_without_calibration_feedback():
    data, inventory = fixture()
    changed, receipt = predictive_roles(data, inventory)
    assert changed['keep'].tolist() == [False, False, False, True, True, True]
    assert data['keep'].tolist() == [True, False, True, True, True, True]
    e = changed['entries'][0]
    assert e['observation_ids'] == ['a', 'c'] and e['alias'] == 2
    assert changed['scan'].tracks[e['track_index']]['observation_ids'] == ['a', 'c']
    np.testing.assert_allclose(changed['scan'].tracks[e['track_index']]['values'], [1, 3])
    assert receipt['demoted'][0]['predictive_variance_multiplier'] == 10
    sigma = changed['scan'].fixed_window_noise['per_observation_noise_sigma_hz']
    assert sigma['a'] == pytest.approx(40/np.sqrt(.2))
    assert sigma['b'] == sigma['d'] == 40
    assert data['scan'].fixed_window_noise['per_observation_noise_sigma_hz']['a'] == 99


def test_no_role_change_preserves_original_noise_and_requires_matching_inventory():
    data, inventory = fixture()
    changed, receipt = predictive_roles(data, dict(rows=[]))
    assert changed['scan'].fixed_window_noise is data['scan'].fixed_window_noise
    assert receipt['demoted'] == []
    inventory['rows'][0]['observation_ids'] = ['a', 'b']
    with pytest.raises(ValueError, match='match original'):
        predictive_roles(data, inventory)
