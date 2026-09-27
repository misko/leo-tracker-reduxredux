"""Shared stationary location with independent scan timing and held-visit audits."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parent
sys.path.insert(0,str(REPORTS/'2026_09_27_ds6_group_consistency'))
from run_groups import load, ScaledObjective


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Joint:
    def __init__(self,models):
        self.models=models

    def evaluate(self,x):
        rows=[model.evaluate(np.array([x[0],x[1],x[2+i]])) for i,model in enumerate(self.models)]
        return dict(train=sum(r['train'] for r in rows),held=sum(r['held'] for r in rows))


def freeze():
    parent=REPORTS/'2026_09_27_ds6_group_consistency'
    old=json.loads((parent/'protocol.json').read_text())
    paths=[parent/'protocol.json',parent/'run_groups.py']
    paths += [REPORTS/name for name in {**old['dependencies'],**old['inputs']}]
    protocol=dict(sessions=old['sessions'],source_sha256=digest(Path(__file__)),
        files={str(p.relative_to(REPORTS)):digest(p) for p in paths},
        center=old['center'],fits='All four, plus each scan omitted in turn',
        model='Shared east/north location; independent timing per included scan; frozen per-track noise and catalogue mixtures',
        starts='Mean of included scan training positions; donor center; each with existing included timing estimates',
        bounds='East/north +/-12 km about donor center; each timing +/-5 seconds',
        selection='Sum of included scan training likelihood; held data never select fit',
        omitted_evaluation='Freeze shared position, adapt omitted scan timing on its training visits only, score its held visits',
        limitation='Four development scans, inherited training calibrations and local approximate catalogue banks; not DS6-wide or blinded validation')
    with (HERE/'protocol.json').open('x') as f:json.dump(protocol,f,indent=2)


def fit_joint(models,positions):
    objective=Joint(models)
    times=[p[2] for p in positions]
    starts=[np.r_[np.mean([p[:2] for p in positions],axis=0),times],np.r_[0.,0.,times]]
    bounds=[(-12.,12.)]*2+[(-5.,5.)]*len(models)
    runs=[]
    for start in starts:
        fit=minimize(lambda x:-objective.evaluate(x)['train'],start,method='L-BFGS-B',bounds=bounds,
            options=dict(maxiter=100,maxfun=1200,ftol=1e-10,gtol=1e-5,eps=1e-4))
        score=objective.evaluate(fit.x)
        runs.append(dict(x=fit.x.tolist(),train=score['train'],held=score['held'],success=bool(fit.success),
            message=str(fit.message),nfev=int(fit.nfev),
            bound_hit=bool(any(abs(v)>=b-1e-3 for v,b in zip(fit.x,[12.,12.]+[5.]*len(models))))))
    return max(runs,key=lambda r:r['train']),runs


def run():
    output=HERE/'results.json'
    if output.exists():raise FileExistsError(output)
    protocol=json.loads((HERE/'protocol.json').read_text())
    assert digest(Path(__file__))==protocol['source_sha256']
    for name,value in protocol['files'].items():assert digest(REPORTS/name)==value
    models={};positions={};bankmakers={}
    for session in protocol['sessions']:
        p,tracks,bank,banks,size,x0=load(session)
        models[session]=ScaledObjective(tracks,bank,p['center'],size,[])
        positions[session]=x0;bankmakers[session]=banks
        print('Loaded '+session,flush=True)
    results={}
    for omitted in [None]+protocol['sessions']:
        included=[s for s in protocol['sessions'] if s!=omitted]
        best,runs=fit_joint([models[s] for s in included],[positions[s] for s in included])
        x=np.array(best['x']);lat,lon=models[included[0]].coordinates(x)
        audits={}
        for i,session in enumerate(included):
            model=models[session];q=np.r_[x[:2],x[2+i]]
            exact=model.evaluate(q,exact_banks=bankmakers[session](np.array([q[2]])))
            base=model.evaluate(positions[session],exact_banks=bankmakers[session](np.array([positions[session][2]])))
            audits[session]=dict(timing_s=float(q[2]),held=exact['held'],held_gain_vs_independent=exact['held']-base['held'])
        adapted=None
        if omitted is not None:
            model=models[omitted];attempts=[]
            for tau in [positions[omitted][2],-2.,2.]:
                fit=minimize(lambda t:-model.evaluate(np.r_[x[:2],t[0]])['train'],np.array([tau]),
                    method='L-BFGS-B',bounds=[(-5.,5.)],options=dict(maxiter=70,ftol=1e-10,eps=1e-4))
                score=model.evaluate(np.r_[x[:2],fit.x[0]])
                attempts.append(dict(timing_s=float(fit.x[0]),train=score['train'],held=score['held'],success=bool(fit.success)))
            selected=max(attempts,key=lambda r:r['train']);tau=selected['timing_s']
            score=model.evaluate(np.r_[x[:2],tau],exact_banks=bankmakers[omitted](np.array([tau])))
            base=model.evaluate(positions[omitted],exact_banks=bankmakers[omitted](np.array([positions[omitted][2]])))
            adapted=dict(attempts=attempts,selected=selected,exact_held=score['held'],held_gain_vs_independent=score['held']-base['held'])
        name='all' if omitted is None else 'without_'+omitted
        results[name]=dict(included=included,omitted=omitted,best=best,runs=runs,latitude=lat,longitude=lon,
            included_audits=audits,omitted_adaptation=adapted)
        output.write_text(json.dumps(dict(protocol_sha256=digest(HERE/'protocol.json'),complete=len(results)==5,fits=results),indent=2)+'\n')
        print(json.dumps(dict(fit=name,latitude=lat,longitude=lon,best=best,omitted_held_gain=None if adapted is None else adapted['held_gain_vs_independent'])),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--freeze',action='store_true');args=parser.parse_args()
    if args.freeze:freeze()
    else:run()
