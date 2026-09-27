"""Training-only track influence and matched single-track deletion diagnostics."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parent
sys.path.insert(0,str(REPORTS/'2026_09_27_ds6_fresh_joint43'))
from run_joint43 import load_model,Objective


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def derivatives(function,x,steps):
    """Central derivatives of a vector of independent track losses."""
    value=np.asarray(function(x));gradient=np.zeros((len(value),3));hessian=np.zeros((len(value),3,3))
    for i in range(3):
        delta=np.eye(3)[i]*steps[i];plus=function(x+delta);minus=function(x-delta)
        gradient[:,i]=(plus-minus)/(2*steps[i])
        hessian[:,i,i]=(plus-2*value+minus)/steps[i]**2
        for j in range(i):
            other=np.eye(3)[j]*steps[j]
            hessian[:,i,j]=hessian[:,j,i]=(function(x+delta+other)-function(x+delta-other)-function(x-delta+other)+function(x-delta-other))/(4*steps[i]*steps[j])
    return value,gradient,hessian


def deletion_shift(gradient,information):
    if np.min(np.linalg.eigvalsh(information))<=1e-6 or np.linalg.cond(information)>1e10:
        return None
    return np.linalg.solve(information,gradient)


def choose(rows,session,seed):
    ranked=sorted(rows,key=lambda r:(r['predicted_shift'] is not None,-r['predicted_horizontal_km'],r['track_id']))
    top=[r['track_id'] for r in ranked[:3]]
    remainder=sorted((r['track_id'] for r in rows if r['track_id'] not in top),key=lambda t:hashlib.sha256(f'{seed}:{session}:{t}'.encode()).hexdigest())
    return top,remainder[:3]


def freeze():
    old_path=REPORTS/'2026_09_27_ds6_fresh_joint43/protocol.json';old=json.loads(old_path.read_text())
    dev=json.loads((REPORTS/'2026_09_27_ds6_curvature_refit/protocol.json').read_text())['development_sessions']
    paths=[old_path,REPORTS/'2026_09_27_ds6_fresh_joint43/run_joint43.py']+[REPORTS/name for name in old['files']]
    protocol=dict(source_sha256=digest(Path(__file__)),files={str(p.relative_to(REPORTS)):digest(p) for p in paths},
        sessions=dev,center=old['center'],seed=2026092737,steps=[.05,.05,.01],
        selection='Top3 training-only predicted horizontal deletion influence (non-positive information first), plus3 hash-random other tracks; no truth selection',
        model='Unchanged fresh-element Student-t4 fixed100Hz mixture; retained training observations only',
        refits='Remove exactly one selected track; starts frozen baseline winner and donor center at baseline tau; same +/-12km, +/-5s bounds',
        scope='Diagnostic influence, not automatic rejection, independent holdout validation, or a new claimed production estimator')
    with (HERE/'protocol.json').open('x') as f:json.dump(protocol,f,indent=2)


def run(session):
    protocol=json.loads((HERE/'protocol.json').read_text());assert session in protocol['sessions']
    assert digest(Path(__file__))==protocol['source_sha256']
    for name,value in protocol['files'].items():assert digest(REPORTS/name)==value
    output=HERE/f'{session}.json'
    if output.exists():raise FileExistsError(output)
    full,x0,banks=load_model(session,protocol['center'])
    individual=[Objective([t],{t['track_id']:full.banks[t['track_id']]},full.center,full.catalogue_size,full.receivers) for t in full.tracks]
    def losses(x):return np.array([-m.evaluate(x,False)['train'] for m in individual])
    values,grad,hess=derivatives(losses,x0,np.array(protocol['steps']))
    _,grad2,hess2=derivatives(losses,x0,np.array(protocol['steps'])/2)
    information=hess.sum(axis=0);rows=[]
    for i,t in enumerate(full.tracks):
        # Include the small nonzero total gradient at the numerical baseline.
        shift=deletion_shift(grad[i]-grad.sum(axis=0),information-hess[i])
        other=deletion_shift(grad2[i]-grad2.sum(axis=0),hess2.sum(axis=0)-hess2[i])
        rows.append(dict(track_id=t['track_id'],receiver_id=t['receiver_id'],span_s=float(np.ptp(t['t'])),
            training_observations=int(t['mask'].sum()),held_observations=int((~t['mask']).sum()),
            gradient=grad[i].tolist(),information=hess[i].tolist(),predicted_shift=None if shift is None else shift.tolist(),
            predicted_horizontal_km=float(np.linalg.norm(shift[:2])) if shift is not None else 0.,
            half_step_predicted_shift=None if other is None else other.tolist()))
    top,random=choose(rows,session,protocol['seed']);fits=[]
    for track_id in top+random:
        omitted=next(m for m in individual if m.tracks[0]['track_id']==track_id)
        tracks=[t for t in full.tracks if t['track_id']!=track_id]
        model=Objective(tracks,full.banks,full.center,full.catalogue_size,full.receivers);runs=[]
        for initial in [x0,np.array([0.,0.,x0[2]])]:
            result=minimize(lambda x:-model.evaluate(x,False)['train'],initial,method='L-BFGS-B',
                bounds=[(-12.,12.),(-12.,12.),(-5.,5.)],options=dict(maxiter=100,maxfun=900,ftol=1e-10,gtol=1e-5,eps=1e-4))
            score=model.evaluate(result.x,False);lat,lon=model.coordinates(result.x)
            runs.append(dict(x=result.x.tolist(),latitude=lat,longitude=lon,train=score['train'],held=score['held'],
                success=bool(result.success),message=str(result.message),nfev=int(result.nfev),
                bound_hit=bool(any(abs(v)>=b-1e-3 for v,b in zip(result.x,[12.,12.,5.])))))
        best=max(runs,key=lambda r:r['train']);x=np.array(best['x']);exact=banks(np.array([x[2]]));original=banks(np.array([x0[2]]))
        exact_score=model.evaluate(x,False,exact_banks=exact);approx=model.evaluate(x,False)
        deviation=max(float(np.max(np.abs(a-b))) for a,b in zip(exact_score['predictions'],approx['predictions'],strict=True))
        row=dict(track_id=track_id,selection='influence' if track_id in top else 'random_control',runs=runs,best=best,
            actual_shift=(x-x0).tolist(),exact_retained_held_gain=exact_score['held']-model.evaluate(x0,False,exact_banks=original)['held'],
            exact_omitted_held_gain=omitted.evaluate(x,False,exact_banks=exact)['held']-omitted.evaluate(x0,False,exact_banks=original)['held'],
            maximum_interpolation_error_hz=deviation)
        fits.append(row);print(json.dumps(dict(session=session,track=track_id,shift=row['actual_shift'],success=best['success'])),flush=True)
    result=dict(session_id=session,complete=True,protocol_sha256=digest(HERE/'protocol.json'),baseline_x=x0.tolist(),
        total_gradient=grad.sum(axis=0).tolist(),information=information.tolist(),tracks=rows,
        selected=dict(influence=top,random_control=random),fits=fits)
    with output.open('x') as f:json.dump(result,f,indent=2)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--freeze',action='store_true');parser.add_argument('--session');args=parser.parse_args()
    if args.freeze:freeze()
    else:run(args.session)
