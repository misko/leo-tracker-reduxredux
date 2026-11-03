from types import SimpleNamespace

import numpy as np

import ds23_reception_geometry as tool


def test_null_geometry_returns_unmodified_original(monkeypatch):
    expected={'features':np.arange(6).reshape(2,3)}
    monkeypatch.setattr(tool,'geometry_features',lambda *args:expected)
    assert tool.physical_geometry(None,[0,0],enabled=False) is expected


def test_reception_geometry_consistently_changes_base_phase_and_orbit_columns(monkeypatch):
    times=np.array([20.,40.,60.]);q=np.array([1.,1.1,.9])
    original=dict(features=np.ones((3,8)),frequency=np.zeros(3),elevation=np.ones(3),
                  derivative=np.zeros(3),intercept=np.zeros(3))
    monkeypatch.setattr(tool,'geometry_features',lambda *args:original)
    p=SimpleNamespace(hardware=np.ones((3,1)),smooth=np.ones((3,1)),labels=[0],
                      reference=np.array([2.]),phase_sigma=np.array([3.]),
                      flat_labels=np.zeros(3,int),flat_times=times,q=q,
                      supported_local=[0],sky='base',mode_bank='modes')
    def states(bank,t,labels,phases):
        r=np.zeros((len(t),3));v=np.zeros_like(r)
        if bank=='base':
            r[:,0]=t+phases[labels]
        else:
            r[:,0]=labels+1
        return r,v
    def frequency(states,t,site,relativistic):
        r,_=states(t)
        return r[:,0]**2,np.zeros(len(t))
    monkeypatch.setattr(tool,'paired_phase_states',states)
    monkeypatch.setattr(tool,'reception_frequency',frequency)
    g=tool.physical_geometry(p,[0,0])
    s=times+2
    np.testing.assert_allclose(g['frequency'],s*s)
    np.testing.assert_allclose(g['derivative'],2*s)
    np.testing.assert_allclose(g['intercept'],s*s-4*s)
    np.testing.assert_allclose(g['features'][:,2],q*2*s*3)
    np.testing.assert_allclose(g['features'][:,3:6],q[:,None]*(2*s[:,None])*np.array([1,2,3]))
    np.testing.assert_array_equal(g['features'][:,:2],original['features'][:,:2])
    np.testing.assert_array_equal(g['features'][:,6:],original['features'][:,6:])
    np.testing.assert_array_equal(original['features'],np.ones((3,8)))
