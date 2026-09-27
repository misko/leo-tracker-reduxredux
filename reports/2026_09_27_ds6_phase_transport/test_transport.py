import importlib.util
from pathlib import Path
import numpy as np
spec=importlib.util.spec_from_file_location('transport',Path(__file__).with_name('run.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_midpoint_transport_recovers_global_phase_and_preserves_difference():
    delta=684012.345;rate=23.17;phi=np.array([.7,-1.2]);mid=np.repeat([.0035,.0245,.0455],8)
    local=np.tile(np.repeat([-.002,-.0005,.001,.0025],2),3);labels=np.tile([-1,1],12);t=mid+local
    intercept=phi[(labels+1)//2]
    raw=np.exp(1j*(intercept+2*np.pi*rate*t+2*np.pi*delta*mid));z=m.transport(raw,mid,delta)
    np.testing.assert_allclose(z,np.exp(1j*(intercept+2*np.pi*rate*t)),atol=1e-10)
    fitted=m.fit(t,z,labels);assert abs(fitted['rate_hz']-rate)<1e-4
    recovered=fitted['source_phases_rad'][1]-fitted['source_phases_rad'][-1]
    assert abs(np.angle(np.exp(1j*(recovered-(phi[1]-phi[0])))))<1e-5
    # A common phase rotation cannot alter simultaneous source DD.
    np.testing.assert_allclose(z[1::2]*z[::2].conj(),raw[1::2]*raw[::2].conj(),atol=1e-10)


def test_training_only_phase_predicts_disjoint_future_samples():
    t=np.linspace(0,.05,31);s=np.where(np.arange(31)%2,1,-1);z=np.exp(1j*(2*np.pi*17.3*t+.9*s))
    model=m.fit(t,z,s)
    held_t=np.linspace(.06,.12,31);held_z=np.exp(1j*(2*np.pi*17.3*held_t+.9*s))
    assert max(abs(m.errors(model,held_t,held_z,s)))<1e-5
    rotated=held_z*np.exp(1j*.4)
    np.testing.assert_allclose(m.errors(model,held_t,rotated,s),.4,atol=1e-5)
