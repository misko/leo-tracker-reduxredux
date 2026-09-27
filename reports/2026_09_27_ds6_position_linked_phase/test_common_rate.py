import importlib.util
from pathlib import Path
import numpy as np

spec=importlib.util.spec_from_file_location('common_rate',Path(__file__).with_name('common_rate.py'))
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_shared_rate_preserves_arbitrary_source_phase_and_time_offsets():
    t=np.r_[np.arange(5)/750-.003,np.arange(4)/750-.0023]
    labels=np.r_[np.full(5,-1),np.full(4,1)]
    for dd in [-2.8,0.4,2.3]:
        z=np.exp(1j*(.7+labels*dd/2+2*np.pi*45.6*t))
        rate,phases=module.fit_rate(t,z,labels)
        assert abs(rate-45.6)<1e-4
        assert abs(np.angle(np.exp(1j*(phases[1]-phases[-1]-dd))))<1e-6


def test_evaluation_cannot_change_rate_or_training_phase():
    t=np.tile(np.arange(5)/750-.003,2)
    labels=np.repeat([-1,1],5)
    z=np.exp(1j*(.6+labels*.4+2*np.pi*17*t))
    fit=dict(t=t,z=z,s=labels)
    first=module.estimate(dict(fit=fit,evaluation=fit),True)
    changed=dict(t=t,z=z*np.exp(1j*labels*.8),s=labels)
    second=module.estimate(dict(fit=fit,evaluation=changed),True)
    assert first['rates_hz']==second['rates_hz']
    assert first['train_dd']==second['train_dd']
    assert abs(np.angle(np.exp(1j*(second['evaluation_dd']-first['evaluation_dd']-1.6))))<1e-8
