from types import SimpleNamespace

import numpy as np
import pytest

from ds23_graph_seeded_path_recovery import receiver_basis,geometry_view,append_native_paths
from ds23_receiver_family_search import fine_receiver_basis
from ds23_predictive_linear import linear_geometry
from leo.analysis.research.retained_track_likelihood import projected_receiver_basis,whitening


@pytest.mark.parametrize('basis',[projected_receiver_basis,fine_receiver_basis])
def test_native_geometry_agrees_with_original_track_feature_builder(basis):
    t=np.linspace(2,270,17);b=basis(t);rf=11.2e9
    track=dict(times=t,values=np.arange(len(t)),receiver=2,channel=3,rf_hz=rf,observation_ids=[str(i) for i in range(len(t))])
    scan=SimpleNamespace(tracks=[track],rx_basis=[b],radio_sigma_hz=100.,fixed_window_noise=dict(extra_parameter_BIC_gain=0,per_observation_noise_sigma_hz={}))
    p=SimpleNamespace(scan=scan,rows=[dict(candidate_index=4)],slices=[slice(0,len(t))],keep=np.ones(len(t),bool),
        hardware=np.zeros((len(t),9)),smooth=np.zeros((len(t),2*b.shape[1])),constants=np.zeros((len(t),1)),labels=[4],members=[0],fitted_c=True)
    observations=[dict(time_s=x,receiver=2,channel=3,actual_rf_hz=rf) for x in t]
    view,active=geometry_view(p,observations,receiver_basis(scan))
    reference,*_=linear_geometry(p,[dict(track_index=0,candidate_index=4,alias=0)])
    assert active==[4]
    for name in ['flat_times','flat_labels','q','hardware','smooth','constants']:
        np.testing.assert_allclose(getattr(view,name),getattr(reference,name),atol=1e-10)


def test_unknown_basis_is_rejected_even_when_its_width_matches():
    t=np.linspace(0,300,10);scan=SimpleNamespace(tracks=[dict(times=t)],rx_basis=[projected_receiver_basis(t)+.001])
    with pytest.raises(ValueError,match='unrecognized'):receiver_basis(scan)


def test_appended_paths_keep_fine_basis_and_original_calibration_rows():
    t=np.linspace(0,20,10);b=fine_receiver_basis(t)
    scan=SimpleNamespace(tracks=[dict(times=t)],rx_basis=[b],white=[whitening(t)],index=[np.arange(len(t))],times=t,curved=[0])
    fragment=dict(key='path',times=t[1:],values=np.arange(9.),observation_ids=[str(i) for i in range(9)],
        receiver=1,channel=2,rf_hz=11e9,candidate_index=7,norad=123)
    changed,entries=append_native_paths(scan,[],[fragment],receiver_basis(scan))
    assert changed.curved==[0] and len(scan.tracks)==1
    np.testing.assert_array_equal(changed.rx_basis[0],b)
    np.testing.assert_allclose(changed.rx_basis[1],fine_receiver_basis(t[1:]))
    assert entries[0]['observation_ids']==fragment['observation_ids']


def test_native_path_lookup_keeps_actual_times_in_gaps_and_after_last_graph_point():
    t=np.array([0.,1.,2.]);extra=np.array([.5,3.]);b=fine_receiver_basis(t)
    scan=SimpleNamespace(tracks=[dict(times=t)],rx_basis=[b],white=[whitening(t)],index=[np.arange(3)],times=t,curved=[0])
    fragment=dict(key='path',times=extra,values=np.array([12.,14.]),observation_ids=['native0','native1'],
        receiver=1,channel=2,rf_hz=11e9,candidate_index=7,norad=123)
    changed,entries=append_native_paths(scan,[],[fragment],receiver_basis(scan))
    np.testing.assert_array_equal(changed.times[changed.index[1]],extra)
    np.testing.assert_array_equal(changed.times[changed.index[0]],t)
    np.testing.assert_array_equal(scan.times,t)
    np.testing.assert_array_equal(changed.tracks[1]['values'],fragment['values'])
    assert changed.curved==[0] and entries[0]['points']==2


def test_support_parent_keeps_original_protected_set_when_adding_predictive_paths(monkeypatch):
    import probe_ds23_graph_seeded_paths as driver
    observed={};sentinel=object()
    def make(*args):observed['protected']=args[-1];return sentinel
    monkeypatch.setattr(driver,'make_problem',make)
    monkeypatch.setattr(driver,'attach_event_predictive',lambda p,e,w:observed.update(entries=e))
    monkeypatch.setattr(driver,'cached',lambda p:p)
    data=dict(scan=None,node=None,keep=np.array([True,True]),powers=np.ones(2),means=np.zeros(2),model={},
        original_protected={3},entries=[dict(candidate_index=8)])
    assert driver.build(data,'support','c0',np.zeros(2)) is sentinel
    assert observed['protected']=={3}
    assert observed['entries']==data['entries']


def test_iteration008_following_diagnostic_binds_the_current_raw_directory():
    import diagnose_ds23_iteration008_tracks as diagnostic
    diagnostic.configure()
    assert diagnostic.diagnostic.runner is diagnostic.runner
    assert diagnostic.diagnostic.OUT==diagnostic.OUT
    assert diagnostic.OUT.parent==diagnostic.runner.RAW
