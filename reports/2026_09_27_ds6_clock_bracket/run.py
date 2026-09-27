"""Conditional host-bracket timing sensitivity, never loading roof truth."""
import argparse
import json
import sys
from pathlib import Path
import numpy as np
from scipy.optimize import minimize

HERE=Path(__file__).resolve().parent;REPORTS=HERE.parent
sys.path.insert(0,str(REPORTS/'2026_09_27_ds6_full_stationary'))
from run_full import Stationary,load_model,digest


def bracket(data):
    t=data['timing'];assert t['qualified']
    assert data['start_utc_ns']==t['first_sample_estimate_utc_ns']
    lo=(t['first_sample_earliest_utc_ns']-data['start_utc_ns'])/1e9
    hi=(t['first_sample_latest_utc_ns']-data['start_utc_ns'])/1e9
    assert -5<lo<0<hi<5
    return lo,hi


def freeze():
    full=REPORTS/'2026_09_27_ds6_full_stationary';p=json.loads((full/'protocol.json').read_text())
    files=[full/'protocol.json',full/'run_full.py']+[REPORTS/f for f in p['files']]
    files += [full/f'{s}.json' for s in p['sessions']]
    files += [REPORTS/'2026_09_27_ds6_cfo_dataset'/f'{s}-plan.json' for s in p['sessions']]
    audit=[]
    for session in p['sessions']:
        data=json.loads((REPORTS/'2026_09_27_ds6_cfo_dataset'/f'{session}-plan.json').read_text())
        lo,hi=bracket(data);tau=json.loads((full/f'{session}.json').read_text())['best']['x'][2]
        audit.append(dict(session_id=session,lower_s=lo,upper_s=hi,baseline_tau_s=tau,outside=not lo<=tau<=hi))
    protocol=dict(source_sha256=digest(HERE/'run.py'),files={str(f.relative_to(REPORTS)):digest(f) for f in files},
        sessions=p['development_sessions'],center=p['center'],timing_audit=audit,
        selection='Same four development sessions frozen before earlier curvature work; no new error-based selection',
        treatment='Restrict shared scan tau to its recorded first-sample host UTC bracket; all other stationary objective and candidate settings unchanged',
        starts='Corrected independent horizontal position at lower bracket, zero, and upper bracket; select training winner',
        limits='Conditional on absolute host UTC accuracy, not independently verified here; effective fitted tau also absorbs orbit/model error; local inherited shortlists; no claim bracket is a hard physical truth')
    with (HERE/'protocol.json').open('x') as f:json.dump(protocol,f,indent=2)


def run(session):
    output=HERE/f'{session}.json'
    if output.exists():raise FileExistsError(output)
    p=json.loads((HERE/'protocol.json').read_text());assert session in p['sessions']
    assert digest(HERE/'run.py')==p['source_sha256']
    for path,value in p['files'].items():assert digest(REPORTS/path)==value
    data=json.loads((REPORTS/'2026_09_27_ds6_cfo_dataset'/f'{session}-plan.json').read_text());lo,hi=bracket(data)
    old=json.loads((REPORTS/'2026_09_27_ds6_full_stationary'/f'{session}.json').read_text())
    base,_,banks=load_model(session,p['center']);model=Stationary(base);runs=[]
    for tau in [lo,0.,hi]:
        start=np.r_[old['best']['x'][:2],tau]
        fit=minimize(model.value_gradient,start,jac=True,method='L-BFGS-B',bounds=[(-12,12),(-12,12),(lo,hi)],
            options=dict(maxiter=100,maxfun=200,ftol=1e-10,gtol=1e-5,maxls=30))
        r=model.evaluate(fit.x);lat,lon=base.coordinates(fit.x)
        row=dict(x=fit.x.tolist(),latitude=lat,longitude=lon,train=r['train'],held=r['held'],
            success=bool(fit.success),message=str(fit.message),nfev=int(fit.nfev),
            horizontal_bound_hit=bool(any(abs(v)>=11.999 for v in fit.x[:2])),
            timing_bound_hit=bool(min(abs(fit.x[2]-lo),abs(fit.x[2]-hi))<1e-5))
        runs.append(row);print(json.dumps(row),flush=True)
    best=max(runs,key=lambda r:r['train']);x=np.array(best['x'])
    approx=model.evaluate(x);exact=model.evaluate(x,exact=banks(np.array([x[2]])))
    deviation=max(float(np.max(np.abs(a-b))) for a,b in zip(exact['predictions'],approx['predictions'],strict=True))
    result=dict(session_id=session,complete=True,protocol_sha256=digest(HERE/'protocol.json'),best=best,runs=runs,
        exact_train=exact['train'],exact_held=exact['held'],held_gain=exact['held']-old['exact_held'],
        max_offset_gradient=exact['max_offset_gradient'],maximum_interpolation_error_hz=deviation)
    with output.open('x') as f:json.dump(result,f,indent=2)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--freeze',action='store_true');p.add_argument('--session');a=p.parse_args()
    if a.freeze:freeze()
    else:run(a.session)
