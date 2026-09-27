"""Full-DS6 stationary-position fit with sparse scan-local timing gradients."""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parent
sys.path.insert(0,str(REPORTS/'2026_09_27_ds6_full_cfo'))
from run_baseline import (Objective,TleArchiveReader,exclude_labelled_starlink_debris,
    parse_element_sets,propagate_candidate_states)


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


class SparseJoint:
    def __init__(self,models):
        self.models=models;self.calls=0

    def value_gradient(self,x):
        value=0.;gradient=np.zeros_like(x);step=1e-4
        for i,model in enumerate(self.models):
            p=np.array([x[0],x[1],x[i+2]])
            base=model.evaluate(p,False)['train'];value+=base
            for local,global_index in [(0,0),(1,1),(2,i+2)]:
                shifted=p.copy();shifted[local]+=step
                # Stay inside the precomputed timing interval at its upper bound.
                delta=-step if local==2 and shifted[local]>5. else step
                shifted[local]=p[local]+delta
                gradient[global_index]+=(model.evaluate(shifted,False)['train']-base)/delta
        self.calls+=1
        if self.calls%25==0:print(json.dumps(dict(evaluations=self.calls,train=value)),flush=True)
        return -float(value),-gradient


def freeze():
    base=REPORTS/'2026_09_27_ds6_full_cfo';old=json.loads((base/'protocol.json').read_text())
    seed=2026092729
    ordered=sorted(old['sessions'],key=lambda s:hashlib.sha256(f'{seed}:{s}'.encode()).hexdigest())
    splits={'all':old['sessions'],'A':ordered[::2],'B':ordered[1::2]}
    files=[base/'protocol.json',base/'run_baseline.py']+[REPORTS/name for name in old['files']]
    files += [REPORTS/folder/f'{s}{suffix}.json' for s in old['sessions'] for folder,suffix in
        [('2026_09_27_ds6_full_cfo',''),('2026_09_27_ds6_cfo_dataset','-plan')]]
    protocol=dict(source_sha256=digest(Path(__file__)),files={str(p.relative_to(REPORTS)):digest(p) for p in files},
        center=old['center'],seed=seed,splits=splits,
        model='One stationary position; independent scan timing and track offsets; Student-t4 fixed100Hz; inherited catalogue mixtures',
        selection='Training visits of included whole scans only; separate seed-randomized complementary scan subsets A/B',
        starts='Mean of included baseline training positions and donor center, with included baseline timing offsets',
        bounds='Shared east/north +/-12km; scan timing +/-5s',
        compute='Sparse forward finite differences: each scan depends on only two location parameters and its own timing',
        scope='Joint static-site inference across DS6; does not replace or claim sub-km individual-scan performance; no reference loaded')
    with (HERE/'protocol.json').open('x') as f:json.dump(protocol,f,indent=2)


def load_model(session,center):
    data=json.loads((REPORTS/'2026_09_27_ds6_cfo_dataset'/f'{session}-plan.json').read_text())
    baseline=json.loads((REPORTS/'2026_09_27_ds6_full_cfo'/f'{session}.json').read_text())
    chosen=baseline['shortlists'];tracks=[]
    for t in data['tracks']:
        if t['track_id'] not in chosen:continue
        t=dict(t,t=np.array(t['times_s']),y=np.array(t['measured_hz']),mask=np.array(t['training_mask'],dtype=bool))
        t['centered_t']=t['t']-t['t'][t['mask']].mean();tracks.append(t)
    archive=TleArchiveReader(Path('/var/lib/leo/tle'))
    snap=archive.select_latest_before(data['start_utc_ns']-505_000_000_000);assert snap.digest==data['snapshot_digest']
    payload,_=exclude_labelled_starlink_debris(archive.read(snap));cat=parse_element_sets(payload)
    def banks(taus):
        return {t['track_id']:propagate_candidate_states(cat,np.array(chosen[t['track_id']]),data['start_utc_ns'],t['t'],taus) for t in tracks}
    bank=banks(np.arange(-5.,5.001,.25))
    model=Objective(tracks,bank,center,len(cat.satellite_numbers),sorted({t['receiver_id'] for t in tracks}))
    return model,np.array(baseline['best']['x']),banks


def run(name):
    output=HERE/f'{name}.json'
    if output.exists():raise FileExistsError(output)
    protocol=json.loads((HERE/'protocol.json').read_text())
    assert digest(Path(__file__))==protocol['source_sha256']
    for path,value in protocol['files'].items():assert digest(REPORTS/path)==value
    sessions=protocol['splits'][name];models=[];positions=[];bankmakers=[]
    for session in sessions:
        model,x0,banks=load_model(session,protocol['center'])
        models.append(model);positions.append(x0);bankmakers.append(banks)
        print(json.dumps(dict(loaded=len(models),total=len(sessions),session=session)),flush=True)
    timing=[p[2] for p in positions]
    starts=[np.r_[np.mean([p[:2] for p in positions],axis=0),timing],np.r_[0.,0.,timing]]
    objective=SparseJoint(models);runs=[];started=time.monotonic()
    for initial in starts:
        fit=minimize(objective.value_gradient,initial,method='L-BFGS-B',jac=True,
            bounds=[(-12.,12.)]*2+[(-5.,5.)]*len(models),
            options=dict(maxiter=100,maxfun=180,ftol=1e-10,gtol=1e-5,maxls=30))
        lat,lon=models[0].coordinates(fit.x)
        row=dict(x=fit.x.tolist(),latitude=lat,longitude=lon,train=-float(fit.fun),
            success=bool(fit.success),message=str(fit.message),nfev=int(fit.nfev),
            bound_hit=bool(any(abs(v)>=b-1e-3 for v,b in zip(fit.x,[12.,12.]+[5.]*len(models)))))
        runs.append(row);print(json.dumps(dict(fit=name,run=len(runs),**row)),flush=True)
    best=max(runs,key=lambda r:r['train']);x=np.array(best['x']);audits=[]
    for i,(model,banks,session) in enumerate(zip(models,bankmakers,sessions,strict=True)):
        point=np.array([x[0],x[1],x[i+2]])
        approx=model.evaluate(point,False)
        exact=model.evaluate(point,False,exact_banks=banks(np.array([point[2]])))
        base=model.evaluate(positions[i],False,exact_banks=banks(np.array([positions[i][2]])))
        deviation=max(float(np.max(np.abs(a-b))) for a,b in zip(approx['predictions'],exact['predictions'],strict=True))
        audits.append(dict(session_id=session,exact_train=exact['train'],exact_held=exact['held'],
            held_gain_vs_independent=exact['held']-base['held'],maximum_interpolation_error_hz=deviation))
    result=dict(fit=name,complete=True,protocol_sha256=digest(HERE/'protocol.json'),sessions=sessions,
        runs=runs,best=best,audits=audits,elapsed_s=time.monotonic()-started)
    with output.open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps(dict(completed=name,elapsed_s=result['elapsed_s'])),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--freeze',action='store_true');parser.add_argument('--fit',choices=['all','A','B']);args=parser.parse_args()
    if args.freeze:freeze()
    else:run(args.fit)
