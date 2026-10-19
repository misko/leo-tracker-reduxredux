import numpy as np
import pytest
from types import SimpleNamespace
from ds23_refined_noise import curve_noise


def test_predictive_noise_detects_actual_curvature_and_recovers_radio_noise_scale():
    rng=np.random.default_rng(3);t=np.linspace(0,100,60)
    y=1000+30*t+3*t*t+rng.normal(0,8,len(t))
    d=curve_noise(t,y)
    assert d['degree']==2
    assert 7<d['predictive_scatter_hz']<12


def test_noise_learning_is_invariant_to_constant_CFO_and_time_origin():
    t=np.linspace(0,100,45);y=np.sin(t*1.3)*9+.5*t*t
    a=curve_noise(t,y);b=curve_noise(t+500,y+800000)
    assert a['degree']==b['degree']
    assert abs(a['predictive_scatter_hz']-b['predictive_scatter_hz'])<1e-7


def test_noise_learning_requires_supported_finite_data():
    with pytest.raises(ValueError):curve_noise([0,1],[0,1])
    with pytest.raises(ValueError):curve_noise(np.arange(9),[1]*8+[np.nan])


def test_precision_reference_changes_only_constant_and_retains_unmodified_noise(monkeypatch):
    import probe_ds23_history_calibrated_phase as original
    from probe_ds23_refined_precision import precision_problem
    from dsx01_joint_marginal import JointMarginal
    rng=np.random.default_rng(19);features=rng.normal(size=(6,4))
    scan=SimpleNamespace(tracks=[dict(observation_ids=['a','b','c']),dict(observation_ids=['d','e','f'])])
    def fake_problem(*args):
        return SimpleNamespace(hardware=np.zeros((6,1)),smooth=np.zeros((6,0)),
            labels=[0],supported=[],members=[0,1],phase_sigma=np.array([2.]),
            point_noise=np.arange(80.,86.),values=np.arange(6.)*40,q=np.ones(6),noise_groups=np.array([0,0,0,1,1,1]))
    monkeypatch.setattr(original,'problem',fake_problem)
    monkeypatch.setattr(JointMarginal,'calculate',lambda p,x:dict(features=features,intercept=np.zeros(6)))
    mask=np.array([True,True,False,True,True,True]);power=np.array([.6,1.]);means=np.array([.3]);model=dict(multiplier=1.,nu=5.)
    old=original.make_problem(scan,{},mask,'c0',np.zeros(1),power,means,1.,5.)
    new=precision_problem(scan,{},mask,'c0',np.zeros(1),power,means,model,{})
    a,b=old.calculate([0,0]),new.calculate([0,0])
    np.testing.assert_allclose(a['residual'][:-1],b['residual'][:-1],rtol=1e-12,atol=1e-12)
    assert abs(a['negative_twice_elbo']-b['negative_twice_elbo'])<1e-10
    expected=2*np.sum(power[old.noise_groups[mask]])*np.log(40)
    assert abs(np.sum(b['residual']**2)-np.sum(a['residual']**2)-expected)<1e-9
    precise=precision_problem(scan,{},mask,'c0',np.zeros(1),power,means,model,{'b':9.})
    np.testing.assert_array_equal(precise.point_noise,[80,9,82,83,84,85])
    assert np.isfinite(precise.calculate([0,0])['residual']).all()


def test_restoration_adds_only_complete_selected_original_curves_and_never_removes_points():
    from probe_ds23_refined_restoration import restoration_mask
    scan=SimpleNamespace(tracks=[dict(key='a',observation_ids=['a1','a2']),
        dict(key='b',observation_ids=['b1','b2']),dict(key='c',observation_ids=['c1','c2'])])
    p=SimpleNamespace(rows=[{'candidate_norad':n} for n in [1,2,3]],members=[0,1,2],
        slices=[slice(0,2),slice(2,4),slice(4,6)])
    keep=np.array([False,False,True,False,True,True])
    mask,rows=restoration_mask(scan,p,keep,{'a1','a2','b1'})
    np.testing.assert_array_equal(mask,[True,True,True,False,True,True])
    assert np.all(mask[keep]) and rows==[dict(track='a',norad=1,new_points=2,total_points=2)]


def test_local_effective_time_predicts_frequency_under_opposite_chirps():
    from local_pilot_refinement import PilotWorkspace,pilot_wave
    from probe_native_code_carrier import interpolate_periodic
    fs=2500000;n=np.arange(fs//50);t=n/fs;mid=t.mean();epoch=125.3
    template=interpolate_periodic(pilot_wave(fs,'lower'),(n-epoch)*32)
    # Unequal frame amplitudes move the information-weighted instant from midscan.
    envelope=np.where(t<.010,.35,1.)
    for rate in (-2000,2000):
        y=template*envelope*np.exp(2j*np.pi*(120123.4*t+.5*rate*(t-mid)**2))
        p=PilotWorkspace(y,fs,'lower',epoch);r=p.frequency_fit(120123.)
        predicted=120123.4+rate*(p.effective_time(r)-mid)
        assert abs(r['CFO_hz']-predicted)<.2


def test_eccentricity_modes_are_shared_by_family_and_scaled_to_actual_RF():
    from probe_ds23_refined_eccentricity import extra_columns
    a=extra_columns([0,0,1],[1,1.1,1],[[2,3],[2,3],[8,9]],[0,1])
    np.testing.assert_allclose(a,[[2,3,0,0],[2.2,3.3,0,0],[0,0,8,9]])


def test_family_reentry_restores_original_companions_without_unrelated_or_rejected_points():
    from probe_ds23_refined_family_reentry import family_mask
    p=SimpleNamespace(rows=[dict(component=str(i),candidate_index=j,candidate_norad=j) for i,j in enumerate([1,1,2])],
        slices=[slice(0,2),slice(2,4),slice(4,6)])
    keep=np.array([False]*4+[True,False]);selected=np.array([True,True,False,False,True,False])
    original=np.array([True,True,True,False,True,True])
    mask,rows=family_mask(p,keep,selected,original)
    np.testing.assert_array_equal(mask,[True,True,True,False,True,False])
    assert [r['added_points'] for r in rows]==[2,1]
