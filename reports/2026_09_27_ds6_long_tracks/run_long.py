"""Training-duration selection with all-track conditional prediction audit."""
import argparse
import copy
import json
import sys
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
HERE=Path(__file__).resolve().parent;REPORTS=HERE.parent
sys.path.insert(0,str(REPORTS/'2026_09_27_ds6_full_stationary'))
from run_full import Stationary,load_model,digest

def eligible(t,minimum=30.):
    values=np.asarray(t['t'])[np.asarray(t['mask'],dtype=bool)]
    return len(values)>=2 and float(np.ptp(values))>=minimum

def freeze():
    full=REPORTS/'2026_09_27_ds6_full_stationary';p=json.loads((full/'protocol.json').read_text())
    files=[full/'protocol.json',full/'run_full.py']+[REPORTS/f for f in p['files']]
    files += [full/f'{s}.json' for s in p['development_sessions']]
    protocol=dict(source_sha256=digest(HERE/'run_long.py'),files={str(f.relative_to(REPORTS)):digest(f) for f in files},
        sessions=p['development_sessions'],center=p['center'],minimum_training_span_s=30.,
        selection='All inherited tracks with >=30 seconds between first and last training observation; no held support or geographic error used',
        fit='Unchanged stationary t4 offset and candidate model; baseline horizontal position at tau baseline,-2,+2; +/-12km,+/-5s',
        evaluation='Exact all-original-track held prediction at selected location; omitted-track constants profiled on their training observations only after geographic selection',
        limits='Four reused development scans, local inherited candidates; duration is span rather than continuous observation time; conditional omitted-track prediction, not absolute CFO prediction')
    with (HERE/'protocol.json').open('x') as f:json.dump(protocol,f,indent=2)

def run(session):
    output=HERE/f'{session}.json'
    if output.exists():raise FileExistsError(output)
    p=json.loads((HERE/'protocol.json').read_text());assert session in p['sessions']
    assert digest(HERE/'run_long.py')==p['source_sha256']
    for path,value in p['files'].items():assert digest(REPORTS/path)==value
    base,_,banks=load_model(session,p['center']);filtered=copy.copy(base)
    filtered.tracks=[t for t in base.tracks if eligible(t,p['minimum_training_span_s'])]
    assert len(filtered.tracks)>=3
    model=Stationary(filtered);old=json.loads((REPORTS/'2026_09_27_ds6_full_stationary'/f'{session}.json').read_text());runs=[]
    for tau in [old['best']['x'][2],-2.,2.]:
        fit=minimize(model.value_gradient,np.r_[old['best']['x'][:2],tau],jac=True,method='L-BFGS-B',
            bounds=[(-12,12),(-12,12),(-5,5)],options=dict(maxiter=100,maxfun=200,ftol=1e-10,gtol=1e-5,maxls=30))
        r=model.evaluate(fit.x);lat,lon=base.coordinates(fit.x)
        row=dict(x=fit.x.tolist(),latitude=lat,longitude=lon,train=r['train'],held=r['held'],success=bool(fit.success),
            message=str(fit.message),nfev=int(fit.nfev),bound_hit=bool(any(abs(v)>=b-1e-3 for v,b in zip(fit.x,[12,12,5]))))
        runs.append(row);print(json.dumps(row),flush=True)
    best=max(runs,key=lambda r:r['train']);x=np.array(best['x']);exact_banks=banks(np.array([x[2]]))
    all_model=Stationary(base);approx=all_model.evaluate(x);exact=all_model.evaluate(x,exact=exact_banks)
    retained=model.evaluate(x,exact=exact_banks)
    deviation=max(float(np.max(np.abs(a-b))) for a,b in zip(approx['predictions'],exact['predictions'],strict=True))
    result=dict(session_id=session,complete=True,protocol_sha256=digest(HERE/'protocol.json'),runs=runs,best=best,
        retained_tracks=[t['track_id'] for t in filtered.tracks],original_track_count=len(base.tracks),
        exact_all_train=exact['train'],exact_all_held=exact['held'],all_held_gain=exact['held']-old['exact_held'],
        exact_retained_held=retained['held'],exact_omitted_held=exact['held']-retained['held'],
        max_offset_gradient=exact['max_offset_gradient'],maximum_interpolation_error_hz=deviation)
    with output.open('x') as f:json.dump(result,f,indent=2)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--freeze',action='store_true');p.add_argument('--session');a=p.parse_args()
    if a.freeze:freeze()
    else:run(a.session)
