"""Freeze mode-difference calibration in visit73 and test it in visit74."""
import csv
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent

def wrap(x):return np.angle(np.exp(1j*np.asarray(x)))

def main():
    rows=list(csv.DictReader((HERE/'data/observations.csv').open()))
    metadata=json.loads((HERE/'data/metadata.json').read_text())
    mode_rows={(r['visit_index'],r['mode']):r for r in metadata['mode_records']}
    pairs={}
    for visit in (73,74):
        arrays=[]
        for mode in ('m0','m1'):
            rs=sorted([r for r in rows if int(r['visit_index'])==visit and r['mode']==mode],key=lambda r:int(r['device_counter']))
            arrays.append(rs)
        assert all(a['device_counter']==b['device_counter'] for a,b in zip(*arrays))
        counters=np.array([int(r['device_counter']) for r in arrays[0]],dtype=np.int64)
        phases=np.array([[float(r['phase_rad']) for r in group] for group in arrays])
        pairs[visit]=(counters,phases)
    origin=pairs[73][0][0]
    train_t=(pairs[73][0]-origin)/1e7
    held_t=(pairs[74][0]-origin)/1e7
    train_difference=wrap(pairs[73][1][0]-pairs[73][1][1])
    held_difference=wrap(pairs[74][1][0]-pairs[74][1][1])
    predictions={};scores={}
    for degree in (0,1,2):
        coefficients=(np.array([np.angle(np.mean(np.exp(1j*train_difference)))]) if degree==0 else np.polynomial.polynomial.polyfit(train_t,np.unwrap(train_difference),degree))
        prediction=np.polynomial.polynomial.polyval(held_t,coefficients)
        error=wrap(prediction-held_difference)
        scores[str(degree)]=dict(held_windows=len(error),wrapped_rms_deg=float(np.degrees(np.sqrt(np.mean(error**2)))),circular_error_R=float(abs(np.mean(np.exp(1j*error)))),coefficients_rad=coefficients.tolist())
        predictions[degree]=prediction
    association=[]
    # Each mode's canonical frequency and timing lattice are compared without phase.
    for mode in ('m0','m1'):
        a,b=mode_rows[73,mode],mode_rows[74,mode]
        start_delta=int(pairs[74][0][0])-int(pairs[73][0][0])
        lattice_delta=start_delta+b['rx0_epoch_sample']-a['rx0_epoch_sample']
        period=1e7/750
        association.append(dict(mode=mode,canonical_frequency_change_hz=b['canonical_cfo_hz']-a['canonical_cfo_hz'],frame_lattice_mismatch_samples=float((lattice_delta+period/2)%period-period/2)))
    result=dict(training_visit=73,evaluation_visit=74,training_windows=len(train_t),association_diagnostics=association,
        gap_samples=3750,intervening_different_target=False,metrics=scores,
        scope='Conditional same-target candidate continuation. Whole visit73 calibrates target-minus-donor; visit74 target is untouched. Current visit74 donor is required: simultaneous correction, not future-only forecast. No arbitrary visit74 phase offset fitted. Mode association plausible from frequency/timing, emitter identity unproven. Not a cross-retune success.')
    (HERE/'revisit-results.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    fig,ax=plt.subplots(figsize=(10,4),constrained_layout=True)
    ax.plot(train_t*1e3,np.degrees(train_difference),'.',label='Visit73 training difference')
    ax.plot(held_t*1e3,np.degrees(held_difference),'.',label='Visit74 observed difference')
    for degree,label in [(0,'Frozen constant difference'),(1,'Frozen linear difference')]:
        ax.plot(held_t*1e3,np.degrees(wrap(predictions[degree])),'.--',label=label)
    ax.set(xlabel='ms from first visit73 window midpoint',ylabel='m0 − m1 phase (degrees)',ylim=(-185,185),title='Actual adjacent-visit transfer · same target · no held phase calibration')
    ax.legend(fontsize=8)
    fig.savefig(HERE/'revisit-transfer.png',dpi=170)
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
