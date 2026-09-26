"""Inject a known instrument into real cached phasors and recover their input phase.

This is a hybrid simulation, not recovery of the recording's unknown geometry.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent

def main():
    spec=importlib.util.spec_from_file_location('reference_recovery',HERE/'reference/run.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    path=HERE.parent/'improvements/pilot-cache.npz'
    cache=np.load(path)
    original=cache['products']
    t=cache['frame_time_s']
    f=cache['tone_frequency_hz']
    # Known *additional* synthetic effects; existing instrument remains in original.
    added=2*np.pi*(31*t+4*t*t)[:,None]+2*np.pi*f[None,:]*35e-9
    injection=np.exp(1j*(.2+2*np.pi*f*12e-9))
    satellite=original*np.exp(1j*added)
    reference=np.exp(1j*added)*injection[None,:]
    truth=np.angle(np.sum(original,axis=1))
    rng=np.random.default_rng(260927)
    cases={
        'exact_known_reference':(reference,injection),
        'noisy_reference_0p05rad':(reference*np.exp(1j*rng.normal(0,.05,reference.shape)),injection),
        'wrong_injection_phase_0p3rad':(reference,injection*np.exp(.3j)),
    }
    missing=reference.copy();missing[::10]=np.nan+1j*np.nan
    cases['missing_every_tenth_reference']=(missing,injection)
    results={};recovered={}
    for name,(ref,known_path) in cases.items():
        result=module.recover(satellite,ref,known_path,0,cache['training'])
        valid=np.asarray(result['valid'])&cache['held']
        error=np.angle(np.exp(1j*(result['phase_rad'][valid]-truth[valid])))
        results[name]={'held_total':int(cache['held'].sum()),'held_supported':int(valid.sum()),
            'wrapped_rms_deg':float(np.degrees(np.sqrt(np.mean(error**2)))),
            'mean_wrapped_bias_deg':float(np.degrees(np.angle(np.mean(np.exp(1j*error)))))}
        recovered[name]=result['phase_rad']
    assert results['exact_known_reference']['wrapped_rms_deg']<1e-8
    assert abs(results['wrong_injection_phase_0p3rad']['mean_wrapped_bias_deg']-np.degrees(.3))<1e-8
    assert results['missing_every_tenth_reference']['held_supported']<results['missing_every_tenth_reference']['held_total']
    output={'scope':'Hybrid injection test: reconstruct original measured combined phase, not geometric truth.',
        'cache_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'seed':260927,
        'added_instrument':'2pi*(31*t+4*t^2)+2pi*f*35ns',
        'reference_injection':'0.2rad+2pi*f*12ns','results':results}
    (HERE/'injection-replay.json').write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')
    fig,axes=plt.subplots(2,1,figsize=(11,6),sharex=True,constrained_layout=True)
    axes[0].plot(t,np.degrees(truth),'.',ms=4,label='Original measured phase',color='#306988')
    axes[0].plot(t,np.degrees(np.angle(np.sum(satellite,axis=1))),'.',ms=2,alpha=.45,label='Added simulated instrument',color='#bf8754')
    axes[0].set(ylabel='Wrapped phase (degrees)',ylim=(-185,185));axes[0].legend(fontsize=8)
    for name,label in [('exact_known_reference','Exact reference'),('noisy_reference_0p05rad','Noisy reference'),('wrong_injection_phase_0p3rad','Wrong injection calibration')]:
        error=np.degrees(np.angle(np.exp(1j*(recovered[name]-truth))))
        axes[1].plot(t,error,'.',ms=3,label=label)
    axes[1].set(xlabel='Seconds from visit259 start',ylabel='Recovery error (degrees)');axes[1].legend(fontsize=8)
    fig.suptitle('Hybrid test: recover recorded phase after adding a known simulated instrument')
    fig.supxlabel('This preserves the original combined phase; it does not remove the recording’s unknown original receiver phase.',fontsize=9)
    fig.savefig(HERE/'injection-replay.png',dpi=170)
    print(json.dumps(results,indent=2))

if __name__=='__main__':main()
