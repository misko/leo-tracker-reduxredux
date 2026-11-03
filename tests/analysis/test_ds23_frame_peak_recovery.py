import numpy as np
from types import SimpleNamespace

from ds23_frame_peak_recovery import measurement_id, polynomial_screen, select_recoveries


def test_curvature_screen_accepts_curvature_but_not_linear_or_noise_only():
    rng=np.random.default_rng(814)
    times=np.linspace(0,60,60);noise=np.full(len(times),150.)
    curved=30000-100*times-2*times**2+rng.normal(0,70,len(times))
    fit=polynomial_screen(times,curved,noise)
    assert fit['degree']==2
    assert fit['curvature_BIC_gain']>10
    linear=30000-100*times+rng.normal(0,70,len(times))
    assert polynomial_screen(times,linear,noise) is None
    assert polynomial_screen(times,linear,noise,require_curvature=False)['active_curvature'] is False


def test_same_native_alias_has_same_research_identity():
    a=dict(epoch=51.124,cfo=3700.)
    b=dict(epoch=51.124,cfo=3700.+1/4.4e-6)
    assert measurement_id('case',2,1,11e9,1.5,a)==measurement_id('case',2,1,11e9,1.5,b)


def test_retained_original_measurements_are_excluded_before_curve_fit():
    times=np.linspace(0,60,40);values=50000-4*times**2
    anchor=dict(receiver=1,times=times,values=values,observation_ids=[f'a{k}' for k in range(40)])
    observations=[dict(receiver=2,time_s=float(t),actual_rf_hz=11e9,measured_cfo_hz=float(y+9000),
                       observation_id=f'b{k}') for k,(t,y) in enumerate(zip(times,values))]
    pairs=[dict(time_s=float(t),channel=1,rf_hz=11e9,curved_anchor_components=['a'],
                first=dict(epoch=51.,cfo=float(y),margin=.5),
                second=dict(epoch=51.03,cfo=float(y+9000),margin=.5),visit_index=k,
                epoch_difference_samples=.03) for k,(t,y) in enumerate(zip(times,values))]
    meta=dict(constant_radio_sigma_hz=100.,extra_parameter_BIC_gain=0)
    fragments,receipt=select_recoveries('case',{'a':anchor},observations,pairs,
        {f'b{k}' for k in range(40)},meta,include_secondary=True)
    assert not fragments
    assert receipt['rejected']['already_retained_original_winner']==40
    fragments,receipt=select_recoveries('case',{'a':anchor},observations,pairs,set(),meta,include_secondary=False)
    assert len(fragments)==1
    assert receipt['added_original_winners']==40
    np.testing.assert_allclose(fragments[0]['values'],values+9000)


def test_predictive_append_preserves_curved_calibration_population_and_noise():
    from probe_algo03_frame_predictive import append_predictions
    from leo.analysis.research.retained_track_likelihood import whitening, projected_receiver_basis
    times=np.linspace(0,60,40);ids=[f'a{k}' for k in range(40)]
    track=dict(key='anchor',receiver=1,channel=1,rf_hz=11e9,times=times,
               values=50000-4*times**2,observation_ids=ids)
    scan=SimpleNamespace(tracks=[track],index=[np.arange(40)],times=times,curved=[0],
        white=[whitening(times)],rx_basis=[projected_receiver_basis(times)],radio_sigma_hz=100.,
        fixed_window_noise=dict(extra_parameter_BIC_gain=0,per_observation_noise_sigma_hz={i:80. for i in ids}))
    base=SimpleNamespace(rows=[dict(component='anchor',candidate_index=2,candidate_norad=999)],
        members=[0],slices=[slice(0,40)],labels=[2],alias=[0],keep=np.ones(40,bool))
    fragment=dict(key='new',parent_component='anchor',receiver=2,channel=1,rf_hz=11e9,
        times=times,values=track['values']+9000,observation_ids=[f'b{k}' for k in range(40)],
        sigma_hz=np.full(40,150.))
    changed,entries=append_predictions(scan,base,dict(linear_paired_valid=False),[fragment])
    assert scan.curved==changed.curved==[0]
    assert len(scan.tracks)==1 and len(changed.tracks)==2
    assert entries[0]['candidate_index']==2
    assert entries[0]['track_index']==1
    assert changed.fixed_window_noise['per_observation_noise_sigma_hz']['a0']==100.
    assert scan.fixed_window_noise['per_observation_noise_sigma_hz']['a0']==80.
    assert changed.fixed_window_noise['per_observation_noise_sigma_hz']['b0']==150.
