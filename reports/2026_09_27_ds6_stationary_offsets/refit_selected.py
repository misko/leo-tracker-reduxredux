"""Isolate geographic impact of correcting audited tracks only."""
import argparse
import json
import sys
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
from scipy.special import logsumexp
from solver import scores
from audit_stationary import HERE,REPORTS,digest,load_model,site
from run_baseline import Objective,robust_scores,REFERENCE_RF_HZ,LIGHT_KM_S


class Corrected:
    def __init__(self,base,ids):
        self.base=base;self.tracks=[t for t in base.tracks if t['track_id'] in ids]
    def evaluate(self,x,exact_banks=None):
        result=self.base.evaluate(x,False,exact_banks=exact_banks)
        rec,up=site(*self.base.coordinates(x));q=(x[2]+5)*4;lo=min(39,max(0,int(np.floor(q))));weight=q-lo
        train=result['train'];held=result['held'];maximum_gradient=0.
        for t in self.tracks:
            if exact_banks is None:
                p,v,_=self.base.banks[t['track_id']];pos=p[:,lo]*(1-weight)+p[:,lo+1]*weight;vel=v[:,lo]*(1-weight)+v[:,lo+1]*weight
            else:
                p,v,_=exact_banks[t['track_id']];pos=p[:,0];vel=v[:,0]
            unit=pos-rec;unit/=np.linalg.norm(unit,axis=-1)[...,None]
            pred=-REFERENCE_RF_HZ/LIGHT_KM_S*np.sum(unit*vel,axis=-1)
            visible=np.any((unit@up)[:,t['mask']]>=0,axis=-1);residual=t['y'][None,:]-pred
            a,b=robust_scores(residual,t['mask']);c,d,audits=scores(residual,t['mask'])
            assert all(v['converged'] for v in audits)
            maximum_gradient=max(maximum_gradient,max(abs(v['gradient']) for v in audits))
            a,b,c,d=[np.where(visible,v,-np.inf) for v in [a,b,c,d]]
            gain=float(logsumexp(c)-logsumexp(a));train+=gain
            held+=float(logsumexp(d)-logsumexp(b))-gain
        return dict(train=train,held=held,max_offset_gradient=maximum_gradient)


def freeze():
    previous=json.loads((HERE/'protocol.json').read_text())
    audit=json.loads((REPORTS/'2026_09_27_ds6_offset_convergence/protocol.json').read_text())
    # Top two stationary-audit training gains, the prior curvature-sensitive
    # scan, and the previously unconverged scan, chosen without roof errors.
    rows=json.loads((HERE/'summary.json').read_text())['results']
    ordered=sorted(rows,key=lambda r:-r['train_gain'])
    sessions=list(dict.fromkeys([r['session_id'] for r in ordered[:2]]+['scan-fw-a077447f07d9f81f','scan-fw-53ce822d78d476ba']))
    protocol=dict(source_sha256=digest(Path(__file__)),solver_sha256=digest(HERE/'solver.py'),
        audit_protocol_sha256=digest(HERE/'protocol.json'),audit_summary_sha256=digest(HERE/'summary.json'),
        sessions=sessions,selected={s:previous['selected'][s] for s in sessions},center=audit['center'],
        scope='Correct selected audited tracks only; all others retain old12 profiler; diagnostic isolation not full estimator replacement',
        starts='Existing baseline winner and donor center with baseline timing; same +/-12km,+/-5s bounds; training-only selection')
    with (HERE/'refit-protocol.json').open('x') as f:json.dump(protocol,f,indent=2)


def run(session):
    protocol=json.loads((HERE/'refit-protocol.json').read_text());assert session in protocol['sessions']
    assert protocol['source_sha256']==digest(Path(__file__)) and protocol['solver_sha256']==digest(HERE/'solver.py')
    assert protocol['audit_protocol_sha256']==digest(HERE/'protocol.json')
    assert protocol['audit_summary_sha256']==digest(HERE/'summary.json')
    parent=json.loads((REPORTS/'2026_09_27_ds6_offset_convergence/protocol.json').read_text())
    for name,value in parent['files'].items():assert digest(REPORTS/name)==value
    output=HERE/f'{session}-refit.json'
    if output.exists():raise FileExistsError(output)
    base,x0,banks=load_model(session,protocol['center']);model=Corrected(base,protocol['selected'][session]);runs=[]
    for initial in [x0,np.r_[0.,0.,x0[2]]]:
        fit=minimize(lambda x:-model.evaluate(x)['train'],initial,method='L-BFGS-B',bounds=[(-12.,12.),(-12.,12.),(-5.,5.)],
            options=dict(maxiter=100,maxfun=900,ftol=1e-10,gtol=1e-5,eps=1e-4))
        value=model.evaluate(fit.x);lat,lon=base.coordinates(fit.x)
        runs.append(dict(x=fit.x.tolist(),latitude=lat,longitude=lon,**value,success=bool(fit.success),message=str(fit.message),
            nfev=int(fit.nfev),bound_hit=bool(any(abs(v)>=b-1e-3 for v,b in zip(fit.x,[12.,12.,5.])))))
        print(json.dumps(dict(session=session,**runs[-1])),flush=True)
    best=max(runs,key=lambda r:r['train']);x=np.array(best['x']);exact=model.evaluate(x,banks(np.array([x[2]])))
    result=dict(session_id=session,complete=True,protocol_sha256=digest(HERE/'refit-protocol.json'),selected_tracks=protocol['selected'][session],
        runs=runs,best=best,exact=exact,baseline_corrected=model.evaluate(x0),baseline_x=x0.tolist())
    output.write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--freeze',action='store_true');parser.add_argument('--session');args=parser.parse_args()
    if args.freeze:freeze()
    else:run(args.session)
