import importlib.util
from pathlib import Path

import numpy as np

spec=importlib.util.spec_from_file_location('eight_frequency_test',Path(__file__).with_name('model.py'))
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_shared_frequency_recovery_with_independent_frame_gains_and_gradient():
    rng=np.random.default_rng(202);blocks=[]
    for frame in range(8):
        t=np.arange(400)/5e5
        parts=[np.exp(.5j*np.pi*rng.integers(0,4,(400,2))) for _ in range(2)]
        y=sum(p@(rng.normal(size=2)+1j*rng.normal(size=2))*np.exp(2j*np.pi*f*t)
              for p,f in zip(parts,(137.,-211.)))
        blocks.append(dict(parts=parts,times=t,samples=y))
    x=np.array([.1,-.1]);_,g,_=m.profile(blocks,x)
    for k in range(2):
        d=np.eye(2)[k]*1e-5
        assert abs((m.profile(blocks,x+d)[0]-m.profile(blocks,x-d)[0])/2e-5-g[k])<1e-7
    separate=[m.separate_fit(blocks,k)['delta_khz'] for k in range(2)]
    records,best=m.fit_joint(blocks,separate)
    assert all(r['qualified'] for r in records)
    np.testing.assert_allclose(best['delta_khz'],[.137,-.211],atol=1e-5)


def test_pooling_weights_energy_not_frame_count():
    rng=np.random.default_rng(3);blocks=[]
    for amplitude in (1.,10.):
        t=np.arange(50)/1e5
        parts=[rng.normal(size=(50,2))+1j*rng.normal(size=(50,2)) for _ in range(2)]
        y=amplitude*(rng.normal(size=50)+1j*rng.normal(size=50))
        blocks.append(dict(parts=parts,times=t,samples=y))
    weights=np.array([np.sum(abs(b['samples'])**2) for b in blocks]);weights/=sum(weights)
    values=[m.single.profile(b['parts'],b['times'],b['samples'],[0.,0.])[0] for b in blocks]
    assert abs(m.profile(blocks,[0.,0.])[0]-np.dot(weights,values))<1e-12
