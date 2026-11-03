import importlib.util
from pathlib import Path

import numpy as np

spec=importlib.util.spec_from_file_location('joint_frequency_test',Path(__file__).with_name('model.py'))
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def example():
    rng=np.random.default_rng(78);t=np.arange(1600)/2e6
    a=np.exp(.5j*np.pi*rng.integers(0,4,(len(t),3)))
    b=np.exp(.5j*np.pi*rng.integers(0,4,(len(t),3)))
    y=a@np.array([1.,.6j,.4])*np.exp(2j*np.pi*137*t)+b@np.array([.7,.2j,.5])*np.exp(-2j*np.pi*211*t)
    return [a,b],t,y


def test_profile_gradient_and_joint_frequency_recovery():
    parts,t,y=example();x=np.array([.05,-.1])
    loss,g,_,_=m.profile(parts,t,y,x)
    for k in range(2):
        d=np.eye(2)[k]*1e-5
        finite=(m.profile(parts,t,y,x+d)[0]-m.profile(parts,t,y,x-d)[0])/2e-5
        assert abs(finite-g[k])<1e-7
    separate=[m.single_frequency(p,t,y)['delta_khz'] for p in parts]
    records,best=m.joint_fits(parts,t,y,separate)
    assert all(r['qualified'] for r in records)
    np.testing.assert_allclose(best['delta_khz'],[.137,-.211],atol=1e-5)


def test_held_values_do_not_change_gain_fit():
    parts,t,y=example();train=np.arange(len(t))<1000;held=~train
    before=m.profile([p[train] for p in parts],t[train],y[train],[.137,-.211])
    y[held]*=3
    after=m.profile([p[train] for p in parts],t[train],y[train],[.137,-.211])
    np.testing.assert_array_equal(before[2],after[2])
    assert m.held_score(parts,t,y,train,held,[.137,-.211])>.4
