"""Choose causal interpolation or extrapolation of phase-aligned TLE shape."""

import argparse
from pathlib import Path
import numpy as np
from run_algo01_ds23_sample import read,write,sha

STRENGTHS=(0.,.125,.25,.5,.75,1.)


def loss(rows,strength,mode):
    if not rows:return None
    old=np.array([r['old_shape'] for r in rows]);target=np.array([r['next_shape'] for r in rows])
    scale=np.array([r['scale'] for r in rows]);ratio=np.array([r['age_gap_ratio'] for r in rows])[:,None,None]
    factor=strength if mode=='interpolate' else -strength*ratio
    z=(target-factor*old)/scale
    return float(np.log1p(np.mean(z*z,axis=(1,2))).sum())


def select(rows):
    if not rows:return dict(mode='interpolate',strength=0.,transitions=0)
    candidates=[]
    for mode in ('interpolate','extrapolate'):
        for strength in STRENGTHS:
            score=loss(rows,strength,mode)
            penalty=np.log(len(rows))+2*np.log(2) if strength else 0.
            candidates.append(dict(mode=mode,strength=strength,loss=score,criterion=2*score+penalty))
    result=min(candidates,key=lambda r:(r['criterion'],r['strength'],r['mode']))
    return dict(result,transitions=len(rows))


def run(path):
    d=read(path);history_path=path.with_name(path.name.replace('_shape_forecast',''))
    history=read(history_path);assert d['history_sha256']==sha(history_path)
    phase_path=path.with_name(path.name.replace('_shape_forecast','_forecast'));phase=read(phase_path)
    assert d['phase_forecast_sha256']==sha(phase_path) and d['strictly_pre_RF'] and not d['GPS_or_radio_used']
    rows=d['transitions'];cutoff=history['cutoff_utc_ns'];assert all(r['validation_time_ns']<=cutoff for r in rows)
    boundary=phase['temporal_split_boundary_ns'];train=[r for r in rows if r['validation_time_ns']<=boundary]
    validation=[r for r in rows if r['validation_time_ns']>boundary]
    prefix=select(train);full=select(rows)
    baseline=loss(validation,0.,'interpolate');forecast=loss(validation,prefix['strength'],prefix['mode'])
    gain=2*(baseline-forecast) if baseline is not None else 0.
    penalty=float(np.log(max(len(validation),1))+2*np.log(2))
    qualified=len(validation)>=30 and gain>penalty
    chosen=full if qualified else dict(mode='interpolate',strength=0.)
    output=path.with_name(path.name.replace('_shape_forecast','_shape_ensemble'))
    write(output,dict(case=d['case'],chosen=chosen,qualified=qualified,prefix_selection=prefix,all_past_selection=full,
        validation_gain=gain,required_gain=penalty,validation_transitions=len(validation),
        shape_transition_sha256=sha(path),history_sha256=sha(history_path),cutoff_utc_ns=cutoff,
        GPS_or_radio_used=False,strictly_pre_RF=True,source_sha256=sha(Path(__file__)),
        criterion_is_robust_state_prediction_not_calibrated_probability=True))
    print(d['case'],'shape ensemble',chosen['mode'],chosen['strength'],'qualified',qualified,'validation gain',gain,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('shape_transitions',type=Path)
    run(parser.parse_args().shape_transitions)
