"""Freeze first-four diagnostic timing/CFO fits and evaluate four held-out pilots."""
import json
from pathlib import Path
import numpy as np
from diagnose_live_observer3_alignment import BASE,ROOT,RATE,digest


def fit(frames,positions,frequencies):
    return (np.polyfit(frames[:4],positions[:4],1),np.polyfit(frames[:4],frequencies[:4],1))


def main():
    source=BASE/'live-observer3-alignment-v1.json';prior=json.loads(source.read_text())
    for name,sha in prior['input_sha256'].items():assert digest(ROOT/name)==sha
    refs=np.fromfile(BASE/'direct-references.ci16',dtype='<i2').reshape(4,3300,4).astype(float)
    refs=refs[:,:,0]+1j*refs[:,:,1]
    raw=np.fromfile(ROOT/'worker.iq.ci16',dtype='<i2').reshape(-1,2).astype(float)
    iq=raw[:,0]+1j*raw[:,1]
    journal=[json.loads(s) for s in (ROOT/'worker.jsonl').read_text().splitlines()]
    result=dict(scope='first_four_alignment_fit_next_four_prediction',new_rf_samples=0,
                acceptance_gates_changed=False,production_acceptance_evaluated=False,
                diagnostic_rejected_estimates_used_for_training=True,false_alarm_calibrated=False,
                source_sha256=digest(Path(__file__)),prior_sha256=digest(source),cases=[])
    for case in prior['cases']:
        rows=case['measurements'];frames=np.array([r['frame'] for r in rows])
        origin=rows[0]['original_first']
        positions=np.array([r['original_first']-origin+(r['original_phase']+r['local_search']['offset_quarters'])/4
                            -r['frame']*RATE/750 for r in rows])
        frequencies=np.array([r['local_search']['cfo_hz'] for r in rows])
        timing,carrier=fit(frames,positions,frequencies)
        # Explicitly check that held-out localization cannot change either fit.
        changed=positions.copy();changed[4:]+=100
        freq_changed=frequencies.copy();freq_changed[4:]+=10000
        alternate=fit(frames,changed,freq_changed)
        np.testing.assert_array_equal(alternate[0],timing);np.testing.assert_array_equal(alternate[1],carrier)
        measured=[]
        for r in rows[4:]:
            frame=r['frame']
            relative=frame*RATE/750+np.polyval(timing,frame)-(r['original_first']-origin)
            whole,phase=divmod(round(relative*4),4)
            if not 0<=32-whole or not 3268-whole<=3300:
                measured.append(dict(frame=frame,status='reference_extent_exceeded'));continue
            source_row=next(j for j in journal if j['kind']==3 and j['attempt']==case['attempt'] and j['frame']==frame)
            z=iq[source_row['iq_offset']+32:source_row['iq_offset']+3268]
            ref=refs[phase,32-whole:3268-whole];frequency=float(np.polyval(carrier,frame))
            dot=np.vdot(ref,z*np.exp(-2j*np.pi*frequency*np.arange(len(z))/RATE))
            power=float(abs(dot)**2/(np.vdot(ref,ref).real*np.vdot(z,z).real))
            measured.append(dict(frame=frame,status='evaluated',relative_start_quarters=whole*4+phase,
                forecast_cfo_hz=frequency,power=power,diagnostic_local_maximum=r['local_search']['power']))
        result['cases'].append(dict(attempt=case['attempt'],timing_samples_per_frame=float(timing[0]),
            timing_intercept_samples=float(timing[1]),cfo_hz_per_frame=float(carrier[0]),heldout=measured))
        print(case['attempt'],round(timing[0],5),[(r['frame'],round(r.get('power',-1),4)) for r in measured],flush=True)
    with (BASE/'live-observer3-alignment-forecast-v1.json').open('x') as stream:
        json.dump(result,stream,indent=2);stream.write('\n')


if __name__=='__main__':main()
