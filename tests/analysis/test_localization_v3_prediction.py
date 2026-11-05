from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3 import prediction
from leo.analysis.localization_v3.phase_reference import phase_refresh, reference_domain
from leo.analysis.localization_v3.recovery_fragments import append_inactive_fragment
from leo.analysis.localization_v3.recovery_partitions import (
    partition_schedule,
    planned_split,
    require_distinct_annotation,
)


def test_phase_convergence_measures_overflow_before_clipping():
    updated, check = phase_refresh([20., -15.], [15., -15.])
    np.testing.assert_array_equal(updated, [15., -15.])
    assert check['phase_change_s'] == 5. and check['clipped_reference_change_s'] == 0.
    assert check['phase_outside_reference_window'] and check['maximum_phase_overflow_s'] == 5.
    assert not reference_domain([-20.,20.], [5.], [0], [15.])['in_domain']


def test_shifted_partitions_are_distinct_native_holdouts_and_reject_changed_times():
    times, focus = np.arange(0., 300., .5), np.arange(101., 167., 1.)
    seeds, plan = partition_schedule(times, focus)
    assert len(seeds) == 3
    folds = []
    for seed in seeds:
        train, held, split = planned_split(times, focus, seed, plan)
        assert not np.any(train & held)
        assert split['guard_s'] == 2 and split['block_s'] == 12
        folds.append(dict(seed=seed, split=split))
    require_distinct_annotation(dict(folds=folds), dict(partition_plan=plan))
    with pytest.raises(ValueError, match='timestamps changed'):
        planned_split(times, focus+.01, seeds[0], plan)
    bad = deepcopy(folds)
    bad[-1] = bad[0]
    with pytest.raises(ValueError, match='frozen schedule'):
        require_distinct_annotation(dict(folds=bad), dict(partition_plan=plan))


def test_inactive_fragment_keeps_original_arrays_and_receiver_basis():
    t = np.arange(30.)
    parent = dict(key='parent', times=t, values=t**2, observation_ids=[str(i) for i in range(30)])
    original = SimpleNamespace(tracks=[parent], white=[object()], rx_basis=[np.c_[t,t**2]])
    changed, index = append_inactive_fragment(original, 0, set(parent['observation_ids'][:10]))
    fragment = changed.tracks[index]
    assert changed.tracks[0] is parent and len(original.tracks) == 1
    assert fragment['observation_ids'] == parent['observation_ids'][10:]
    np.testing.assert_array_equal(fragment['values'], parent['values'][10:])
    np.testing.assert_array_equal(changed.rx_basis[index], original.rx_basis[0][10:])
    fragment['values'][0] = -123.
    assert parent['values'][10] == 100.
    with pytest.raises(ValueError, match='owned and unowned'):
        append_inactive_fragment(original, 0, set())


def test_training_factory_removes_full_data_noise_and_family_weights(monkeypatch):
    made = SimpleNamespace(values=np.arange(3.), point_noise=np.array([1.,2.,3.]))
    monkeypatch.setattr(prediction, 'make_problem', lambda *args, **kwargs: made)
    p = prediction.training_factory({})(None)
    np.testing.assert_array_equal(p.point_noise, np.full(3,150.))
    # fit_training supplies unit powers even when the original family weights differ.
    captured = []
    def make(*args, **kwargs):
        captured.append(args[5].copy())
        return SimpleNamespace(labels=[0], state=lambda x:dict(phases=np.zeros(1)),
            calculate=lambda x:dict(negative_twice_elbo=1.))
    monkeypatch.setattr(prediction, 'prior_means', lambda *args: (np.zeros(1), []))
    monkeypatch.setattr(prediction, 'make_event_problem', make)
    monkeypatch.setattr(prediction, 'cached', lambda p:p)
    monkeypatch.setattr(prediction, 'fit', lambda *args, **kw:dict(parameters=np.zeros(2)))
    d = dict(scan=None, powers=np.array([.1,.2]), model={}, entries=[])
    prediction.fit_training(d, {}, np.ones(3,bool), 'c0')
    assert len(captured) == 5 and all(np.array_equal(v, [1.,1.]) for v in captured)


def test_nomination_never_reads_held_target_values(monkeypatch):
    t = np.arange(40.)
    track = dict(times=t, values=t*t, rf_hz=11.5e9, receiver=1)
    scan = SimpleNamespace(tracks=[track], sky={}, rx_basis=[np.zeros((40,1))],
        hardware=lambda *args:np.zeros(40),
        search_region=SimpleNamespace(latlon=lambda x:tuple(x)))
    p = SimpleNamespace(scan=scan, state=lambda x:dict(beta=np.zeros(8), smooth=np.zeros((2,1))))
    base = {arm:(p,np.zeros(2),{}) for arm in ('c0','fitted_c')}
    def geometry(bank, times, *args, phase_seconds):
        f = np.stack([(times+phase_seconds)**2+k*times/20 for k in range(3)])
        return f, np.ones_like(f)*30
    monkeypatch.setattr(prediction, 'phase_frequency_grid', geometry)
    keep = np.arange(40)%3 != 0
    first, receipt = prediction.nominate(dict(scan=scan), base, 0, keep, 3)
    track['values'][~keep] += 1e9
    second, another = prediction.nominate(dict(scan=scan), base, 0, keep, 3)
    assert keep[receipt['training_indices']].all()
    for left,right in zip(first,second,strict=True):
        assert left.keys() == right.keys()
        for k in left:
            np.testing.assert_array_equal(left[k], right[k])
    np.testing.assert_array_equal(receipt['training_indices'], another['training_indices'])


def test_uncalibrated_family_uses_causal_phase_mixture_and_preserves_coefficients(monkeypatch):
    track = dict(times=np.array([1.,2.]), rf_hz=11.5e9, receiver=1, channel=8)
    scan = SimpleNamespace(tracks=[track], rx_basis=[np.zeros((2,1))],
        search_region=SimpleNamespace(latlon=lambda x:tuple(x)), sky=dict(time_s=np.arange(3.),
            position_km=np.zeros((1,3,3)), velocity_km_s=np.zeros((1,3,3))))
    coefficient = np.array([10.])
    p = SimpleNamespace(labels=[0], rows=[dict(candidate_index=0)], keep=np.array([False]),
        slices=[slice(0,1)], members=[0], fitted_c=False, events=[],
        calculate=lambda x:dict(coefficient=coefficient))
    monkeypatch.setattr(prediction, 'calibration_covariance',
        lambda *args:(dict(coefficient=coefficient), np.array([[4.]])))
    monkeypatch.setattr(prediction, 'receiver_design', lambda *args, **kw:np.ones((2,1)))
    monkeypatch.setattr(prediction, 'phase_widths', lambda *args:(np.array([2.]), []))
    monkeypatch.setattr(prediction, 'forecast_phase_mean', lambda *args:np.array([1.]))
    monkeypatch.setattr(prediction, 'build_modes', lambda *args:({}, []))
    monkeypatch.setattr(prediction, 'paired_phase_frequency',
        lambda bank,times,labels,phase,*args:(np.ones(2)*phase[0],np.ones(2)*30))
    monkeypatch.setattr(prediction, 'paired_frequency_modes', lambda *args:np.ones((2,1))*3.)
    d = dict(scan=scan, model=dict(shrinkage=.5,multiplier=1.,nu=4.))
    means,cov,lp,phases,_,receipt = prediction.prediction_models(d,p,np.zeros(2),0,0,
        phase_step=5.,uncalibrated_phase_mixture=True)
    assert receipt['kind'] == 'uncalibrated_family_causal_phase_mixture'
    np.testing.assert_array_equal(means[:,0], phases+10.)
    np.testing.assert_array_equal(cov[0], np.eye(2)*45000+90000+4+9)
    assert np.isfinite(lp).all()
    np.testing.assert_array_equal(coefficient,[10.])
    with pytest.raises(ValueError,match='active calibration'):
        p.keep[:] = True
        prediction.check_predictive_role(p,0,True)
