import numpy as np
import pytest
from ds23_frequency_events import event_design,event_profile


def test_receiver_and_band_events_preserve_physical_units_and_scope():
    t=np.array([9.,10.,11.,12.]);rx=np.array([1,1,1,2]);ch=np.array([1,1,6,6]);rf=np.full(4,23e9)
    events=[dict(kind='receiver',receiver=1,time_s=10.,sigma_hz=300),
            dict(kind='receiver_RF',receiver=1,time_s=10.,sigma_hz=300),
            dict(kind='band',receiver=1,band=1,time_s=10.,sigma_hz=300)]
    d=event_design(t,rx,ch,rf,np.zeros(4),events)
    np.testing.assert_allclose(d,[[0,0,0],[300,600,0],[300,600,300],[0,0,0]])


def test_family_event_is_shared_across_receivers_and_rf_scaled():
    e=[dict(kind='family',candidate_index=7,time_s=10.,sigma_hz=100.)]
    d=event_design([11,11,11],[1,2,1],[1,6,3],[11.5e9,23e9,11.5e9],[7,7,9],e)
    np.testing.assert_allclose(d[:,0],[100,200,0])


def test_conditional_bound_matches_direct_data_covariance():
    y=np.array([4.,2.,-3.,8.]);sigma=np.array([2.,3.,2.,4.]);g=np.array([0,0,1,1]);d=np.array([[0],[0],[3],[3.]])
    r=event_profile(y,d,sigma,g,prior_sigma_hz=5)
    u=np.column_stack((d,np.eye(2)[g]*5));cov=np.diag(sigma**2)+u@u.T
    expected=y@np.linalg.solve(cov,y)+np.linalg.slogdet(cov)[1]-np.sum(np.log(sigma**2))
    assert abs(r['cost']-expected)<1e-10


def test_unknown_events_and_negative_noise_fail():
    with pytest.raises(ValueError):event_design([0],[1],[1],[11.5e9],[1],[dict(kind='bad',time_s=0,sigma_hz=2)])
    with pytest.raises(ValueError):event_profile([0],np.zeros((1,0)),[-1],[0])


def test_event_base_factory_is_explicit_and_does_not_replace_the_global_default(monkeypatch):
    import ds23_frequency_events as module
    from types import SimpleNamespace
    p=SimpleNamespace(labels=[0],flat_labels=np.array([0]),flat_times=np.array([1.]),members=[0],q=np.array([1.]),
        calculate=lambda x:None,state=lambda x:None,conditional_frequency=lambda x:None,
        hardware=np.zeros((1,8)),smooth=np.zeros((1,2)),supported=[])
    scan=SimpleNamespace(tracks=[dict(times=np.array([1.]),receiver=1,channel=1)])
    calls=[]
    def supplied(*args):calls.append(args);return p
    def forbidden(*args):raise AssertionError('global factory must not be replaced or invoked')
    monkeypatch.setattr(module,'make_problem',forbidden)
    result=module.make_event_problem(scan,{},np.array([True]),'c0',np.array([0.]),[1.],[0.],dict(multiplier=2.,nu=4.),[],base_problem_factory=supplied)
    assert result is p and result.events==[] and len(calls)==1
    assert module.make_problem is forbidden and calls[0][-2:]==(2.,4.)
