from types import SimpleNamespace
import copy
import numpy as np
import pytest

from ds23_short_whole_curve_view import promote
import probe_ds23_iteration010_short_curves as study


def context():
    tracks=[dict(key=f't{k}',observation_ids=[f'{k}a',f'{k}b'],times=np.array([0.,15.]),values=np.array([10.,20.]),receiver=rx,channel=ch) for k,(rx,ch) in enumerate([(1,1),(1,2),(2,1)])]
    rows=[dict(component='t0',candidate_index=1,candidate_norad=11)]
    data=dict(scan=SimpleNamespace(tracks=tracks,curved=[0]),node=dict(seed=dict(rows=rows),aliases=[0]),keep=np.ones(2,bool),powers=np.array([.6]),entries=[],all_means=np.arange(6.))
    p=SimpleNamespace(members=[0],slices=[slice(0,2)],rows=rows,keep=data['keep'])
    return data,p


def offer(i,j):return dict(track_index=i,candidate_index=j,norad=10+j,alias=1,curvature=dict(qualified=True))


def test_promote_keeps_native_graph_values_ids_basis_and_incumbent_rows():
    d,p=context();before=copy.deepcopy(d)
    changed,added=promote(d,p,[offer(1,2),offer(2,2)])
    assert changed['scan'].curved==[0,1,2] and d['scan'].curved==[0]
    assert changed['keep'].tolist()==[True]*6
    assert changed['node']['seed']['rows'][0]==before['node']['seed']['rows'][0]
    assert changed['powers'].tolist()==[.6,1.,1.]
    assert changed['means'].tolist()==[1.,2.]
    assert changed['scan'].tracks is d['scan'].tracks
    assert [r['power'] for r in added]==[1.,1.]


def test_no_active_overlap_and_no_unqualified_linear_calibration():
    d,p=context();d['entries']=[dict(observation_ids=['1a'])]
    with pytest.raises(ValueError,match='wholly unused'):promote(d,p,[offer(1,2)])
    d['entries']=[];x=offer(1,2);x['curvature']['qualified']=False
    with pytest.raises(ValueError,match='supported curvature'):promote(d,p,[x])


def test_new_existing_family_inherits_frozen_family_power():
    d,p=context();changed,_=promote(d,p,[offer(1,1)])
    assert changed['powers'].tolist()==[.6,.6]


def test_nomination_scales_orbit_mean_and_phase_derivative_once_at_native_rf(monkeypatch):
    captured=[];q=np.array([.9,1.1]);datum=dict(times=np.array([10.,20.]),values=np.zeros(2),radio=np.zeros((2,1)),
        coefficient=np.zeros(1),radio_width=1,q=q,base_covariance=np.eye(2),groups=np.zeros(2,int))
    monkeypatch.setattr(study.binding.paths,'build',lambda *a:None)
    monkeypatch.setattr(study,'group_data',lambda *a:datum)
    monkeypatch.setattr(study,'phase_frequency_grid',lambda sky,t,lat,lon,phase_seconds:(np.ones((2,2))*100+np.asarray(phase_seconds)[:,None]*2,np.ones((2,2))))
    def coarse(*args):captured.append(args);return dict(score=np.array([0.,100.]),aliases=np.zeros((2,1),int))
    monkeypatch.setattr(study,'coarse_phase_scores',coarse)
    monkeypatch.setattr(study,'candidate_prediction',lambda d,data,j,aliases:dict(candidate_index=j,norad=100+j,score=float(j),qualified=True,aliases=aliases))
    monkeypatch.setattr(study,'residual_checks',lambda *a:[dict(compatible=True)])
    arm=dict(endpoint_east_north_km=[0.,0.],phase_reference=[0.,0.])
    d=dict(scan=SimpleNamespace(sky={},norads=[100,101]),arms=dict(c0=arm,fitted_c=arm),all_means=np.zeros(2),widths=np.ones(2))
    result=study.nominate(d,'default',dict(track_index=0,curvature=dict(qualified=True)))
    np.testing.assert_allclose(captured[0][2],np.tile(100*q,(2,1)))
    np.testing.assert_allclose(captured[0][3],np.tile(2*q,(2,1)))
    assert result['offer']['norad']==100
