"""Training-only phase/clock fits with held circular-residual evaluation."""
import hashlib
import json
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares

HERE=Path(__file__).resolve().parent


def wrap(values,period):
    return (np.asarray(values)+period/2)%period-period/2


def fit_phase(times,phase,ranges,mask,period,coefficient):
    times,phase,ranges,mask=map(np.asarray,(times,phase,ranges,mask))
    order=np.argsort(times[mask],kind='stable')
    train_t=times[mask][order]
    if len(train_t)<3 or not np.any(~mask) or np.ptp(train_t)<=0:
        return dict(qualified=False,reason='insufficient_train_or_held_support')
    center=float(np.mean(train_t));scale=float(np.ptp(train_t))
    design=np.column_stack((np.ones(len(times)),(times-center)/scale))
    residual=wrap(phase[mask][order]-coefficient*ranges[mask][order],period)
    unwrapped=np.unwrap(residual,period=period)
    initial=np.linalg.lstsq(design[mask][order],unwrapped,rcond=None)[0]
    fit=least_squares(lambda b:design[mask][order]@b-unwrapped,initial,jac=lambda b:design[mask][order],loss='soft_l1',f_scale=.1,ftol=1e-12,xtol=1e-12,gtol=1e-10,max_nfev=300)
    error=wrap(phase-coefficient*ranges-design@fit.x,period)
    return dict(qualified=bool(fit.success and fit.optimality<1e-4),clock_slope_us_per_s=float(fit.x[1]/scale),phase_origin_us=float(fit.x[0]),train_median_absolute_us=float(np.median(abs(error[mask]))),held_median_absolute_us=float(np.median(abs(error[~mask]))),held_p90_absolute_us=float(np.quantile(abs(error[~mask]),.9)),large_training_steps=int(np.sum(abs(wrap(np.diff(residual),period))>period/4)),optimality=float(fit.optimality),evaluations=int(fit.nfev))


def main():
    sources={str(Path(__file__)):hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    results=[]
    for index in (16,17):
        path=HERE/f'input-{index:02d}.json'
        doc=json.loads(path.read_text());sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        for p,h in doc['sources'].items():assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==h,p
        rows=[]
        for track in doc['rows']:
            points=track['points']
            inputs=([p['frame_time_s'] for p in points],[p['phase_us'] for p in points],[p['range_delay_us'] for p in points],np.array([p['training'] for p in points],bool),doc['frame_period_us'])
            rows.append(dict(track_id=track['track_id'],norad=track['norad'],receiver=track['receiver'],rf_hz=track['rf_hz'],arms={name:fit_phase(*inputs,k) for name,k in [('range',1),('clock_only',0),('reverse',-1)]}))
        eligible=[r for r in rows if all(a['qualified'] for a in r['arms'].values())]
        summary=dict(tracks=len(rows),all_arms_qualified=len(eligible),range_beats_clock=sum(r['arms']['range']['held_median_absolute_us']<r['arms']['clock_only']['held_median_absolute_us'] for r in eligible),range_beats_reverse=sum(r['arms']['range']['held_median_absolute_us']<r['arms']['reverse']['held_median_absolute_us'] for r in eligible),median_track_held_absolute_us={a:float(np.median([r['arms'][a]['held_median_absolute_us'] for r in eligible])) for a in ('range','clock_only','reverse')})
        results.append(dict(index=index,rows=rows,summary=summary))
    result=dict(recordings=results,sources=sources,position_improvement_established=False,scope='approximate range-curvature feasibility, with per-track linear clock nuisance; labels inferred')
    with (HERE/'audit.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps([dict(index=r['index'],**r['summary']) for r in results],indent=2))


if __name__=='__main__':main()
