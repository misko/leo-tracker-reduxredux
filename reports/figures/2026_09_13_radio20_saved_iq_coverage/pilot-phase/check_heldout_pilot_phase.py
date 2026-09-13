"""Diagnostic phase prediction: first four pilots fit, next four held out.

No new detector, gate calibration, acquisition or RF identity claim.
"""
import hashlib,json
from pathlib import Path
import numpy as np

BASE=Path(__file__).parent;ROOT=BASE/'missed-candidate-replay-v1';RATE=2500000
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def predict(time,correlation):
    time=np.asarray(time);a=np.asarray(correlation)
    design=np.column_stack((time-time[0],np.ones(len(time))))
    fitted=np.linalg.lstsq(design[:4],np.unwrap(np.angle(a[:4])),rcond=None)[0]
    predicted=design@fitted
    errors=np.angle(a*np.exp(-1j*predicted))
    held=a[4:8]*np.exp(-1j*predicted[4:8])
    denominator=float(np.vdot(held,held).real)
    return dict(train_residual_cfo_hz=float(fitted[0]/(2*np.pi)),
        phase_error_rad=errors.tolist(),heldout_phase_rms_rad=float(np.sqrt(np.mean(errors[4:8]**2))),
        heldout_coherent_gain=float(abs(held.sum())**2/denominator) if denominator else 0,
        heldout_mean_cos_phase_error=float(np.mean(np.cos(errors[4:8]))))


def main():
    time=np.arange(8)/750
    ideal=.2*np.exp(1j*(.6+2*np.pi*42*time))
    check=predict(time,ideal)
    assert abs(check['train_residual_cfo_hz']-42)<1e-10
    assert check['heldout_phase_rms_rad']<1e-12 and abs(check['heldout_coherent_gain']-4)<1e-12
    opposite=ideal.copy();opposite[4:]*=np.array([1,-1,1,-1])
    assert predict(time,opposite)['heldout_coherent_gain']<1e-20
    manifest=json.loads((ROOT/'result.json').read_text())
    refs=np.fromfile(BASE/'direct-references.ci16',dtype='<i2').reshape(4,3300,4)
    result=dict(scope='first_four_fit_next_four_phase_prediction',new_rf_samples=0,
        acceptance_gates_changed=False,false_alarm_calibrated=False,native_tracking_qualified=False,
        synthetic_invariant_checks=3,source_sha256=digest(Path(__file__)),
        input_manifest_sha256=digest(ROOT/'result.json'),cases=[])
    for case in manifest['cases']:
        root=ROOT/case['label'];assert digest(root/'iq.ci16')==case['input_sha256']
        assert digest(root/'stdout.jsonl')==case['journal_sha256']
        iq=np.fromfile(root/'iq.ci16',dtype='<i2').reshape(-1,2)
        rows=[json.loads(line) for line in (root/'stdout.jsonl').read_text().splitlines()]
        cfo=next(r for r in rows if r['kind']==2)['cfo_hz']
        past=[r for r in rows if r['kind']==3][:8];assert len(past)==8
        first=past[0]['first'];times=[];correlation=[]
        for r in past:
            at=r['first'];refrow=refs[r['reference_phase']]
            ref=refrow[:,0].astype(float)+1j*refrow[:,1]
            raw=iq[at:at+3300].astype(float);z=raw[:,0]+1j*raw[:,1]
            # Common resolver CFO with absolute phase relative to first pilot.
            # No frequency or phase is fitted from the held-out measurements.
            z*=np.exp(-2j*np.pi*cfo*(np.arange(3300)+at-first)/RATE)
            correlation.append(np.vdot(ref,z)/np.sqrt(np.vdot(ref,ref).real*np.vdot(z,z).real))
            times.append(at/RATE)
        checked=predict(times,correlation)
        row=dict(label=case['label'],resolver_cfo_hz=cfo,
            matched_power=[float(abs(a)**2) for a in correlation],
            frame_numbers=[r['frame'] for r in past],source_first=[r['first'] for r in past],
            complex_correlations=[[float(a.real),float(a.imag)] for a in correlation],**checked)
        result['cases'].append(row)
        print(case['label'],checked['heldout_phase_rms_rad'],checked['heldout_coherent_gain'],flush=True)
    with (BASE/'heldout-pilot-phase-v1.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')


if __name__=='__main__':main()
