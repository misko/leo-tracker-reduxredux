"""Diagnostic: separate common quadratic clock curvature from source variation.

Fit per-track quadratic phase and range on training samples only. Median-pool
receiver copies/fragments by inferred physical source, then fit phase curvature
as a common intercept plus beta times orbital curvature on donor16 only. Freeze
that relation and inspect donor17, with no DS11 data. This is explanatory, not a
calibrated position likelihood; short arcs and clock steering remain confounded.
"""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares
from audit import wrap

HERE=Path(__file__).resolve().parent


def curvature(points,period):
    t=np.array([p['frame_time_s'] for p in points]);phase=np.array([p['phase_us'] for p in points]);ranges=np.array([p['range_delay_us'] for p in points]);mask=np.array([p['training'] for p in points],bool)
    if mask.sum()<4 or (~mask).sum()<1 or np.ptp(t[mask])==0:return dict(qualified=False)
    center=np.mean(t[mask]);scale=np.ptp(t[mask]);u=(t-center)/scale
    design=np.column_stack((np.ones(len(t)),u,u*u))
    order=np.argsort(t[mask],kind='stable');y=np.unwrap(phase[mask][order],period=period)
    initial=np.linalg.lstsq(design[mask][order],y,rcond=None)[0]
    fit=least_squares(lambda b:design[mask][order]@b-y,initial,jac=lambda b:design[mask][order],loss='soft_l1',f_scale=.1,ftol=1e-12,xtol=1e-12,gtol=1e-10,max_nfev=300)
    q=np.linalg.lstsq(design[mask],ranges[mask],rcond=None)[0]
    error=wrap(phase-design@fit.x,period)
    return dict(qualified=bool(fit.success and fit.optimality<1e-4),phase_curvature_us_per_s2=float(fit.x[2]/scale**2),range_curvature_us_per_s2=float(q[2]/scale**2),held_median_absolute_us=float(np.median(abs(error[~mask]))),training_span_s=float(scale))


def main():
    paths=[HERE/f'input-{i:02d}.json' for i in (16,17)]
    recordings=[]
    for path in paths:
        doc=json.loads(path.read_text());rows=[];groups=defaultdict(list)
        for row in doc['rows']:
            fit=curvature(row['points'],doc['frame_period_us'])
            rows.append(dict(track_id=row['track_id'],norad=row['norad'],receiver=row['receiver'],**fit))
            if fit['qualified']:groups[row['norad']].append(fit)
        grouped=[dict(norad=n,tracks=len(g),phase=float(np.median([r['phase_curvature_us_per_s2'] for r in g])),orbit=float(np.median([r['range_curvature_us_per_s2'] for r in g]))) for n,g in sorted(groups.items())]
        recordings.append(dict(index=doc['index'],rows=rows,groups=grouped))
    train=recordings[0]['groups'];x=np.array([r['orbit'] for r in train]);y=np.array([r['phase'] for r in train]);design=np.column_stack((np.ones(len(x)),x))
    initial=np.linalg.lstsq(design,y,rcond=None)[0]
    fit=least_squares(lambda b:design@b-y,initial,jac=lambda b:design,loss='soft_l1',f_scale=.01,gtol=1e-12,ftol=1e-12,xtol=1e-12,max_nfev=300)
    summaries=[]
    for doc in recordings:
        phase=np.array([r['phase'] for r in doc['groups']]);orbit=np.array([r['orbit'] for r in doc['groups']]);pred=fit.x[0]+fit.x[1]*orbit
        summaries.append(dict(index=doc['index'],groups=len(phase),tracks_qualified=sum(r['qualified'] for r in doc['rows']),phase_curvature_quantiles=np.quantile(phase,[.1,.5,.9]).tolist(),orbital_curvature_quantiles=np.quantile(orbit,[.1,.5,.9]).tolist(),median_curvature_residual_us_per_s2=float(np.median(abs(phase-pred))),clock_only_median_residual_us_per_s2=float(np.median(abs(phase-np.median(y)))),median_track_quadratic_held_us=float(np.median([r['held_median_absolute_us'] for r in doc['rows'] if r['qualified']]))))
    result=dict(recordings=recordings,training_relation=dict(common_clock_curvature_us_per_s2=float(fit.x[0]),orbital_coefficient=float(fit.x[1]),qualified=bool(fit.success)),summaries=summaries,sources={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths+[Path(__file__),HERE/'audit.py']},position_improvement_established=False)
    with (HERE/'curvature.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps(dict(training_relation=result['training_relation'],summaries=summaries),indent=2))


if __name__=='__main__':main()
