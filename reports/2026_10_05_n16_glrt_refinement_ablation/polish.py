"""Matched common-seed continuation, separating data effects from local basins.

Reprice the same archive + all three stage/RF initial-fit seeds in every case.
Transfer shared satellite timings and baseline RX lines; rank by model score,
never true position error. Keep the original result if no score improvement.
"""
import argparse
import json
import time
from concurrent.futures import ProcessPoolExecutor
from types import SimpleNamespace

import numpy as np
import pipeline as p

BUDGET=dict(ranked_starts=2,start_s=12.,slsqp_s=20.,fisher_s=15.)


def load(path):
    with np.load(path) as z:return SimpleNamespace(**{k:z[k].copy() for k in z.files})


def transfer(seed,old,new):
    params=np.array(seed['parameters']);mapping=dict(zip(old.numbers,params[6:]))
    result=np.r_[params[:6],[mapping.get(n,new.initial[6+i]) for i,n in enumerate(new.numbers)]]
    lookup={int(g):i for i,g in enumerate(old.group)}
    common=np.array([i for i,g in enumerate(new.group) if int(g) in lookup])
    previous=np.array([lookup[int(new.group[i])] for i in common])
    for rx in (0,1):
        mask=new.receiver[common]==rx;ix=common[mask];prior=previous[mask]
        if len(ix)>1:
            x=np.column_stack([np.ones(len(ix)),new.times[ix]-150.])
            result[2+2*rx:4+2*rx]+=np.linalg.lstsq(x,old.fixed_receiver_hz[prior]-new.fixed_receiver_hz[ix],rcond=None)[0]
    return dict(seed,parameters=result)


def run(scan):
    source_records=[];sources={}
    for stage in p.STAGES:
        folder=p.HERE/stage/scan;old=load(folder/'position-input.npz')
        for arm in p.ARMS:
            path=folder/f'position-{arm}.json';record=json.loads(path.read_text())
            source_records.append((f'{stage}-{arm}',record['best'],old));sources[str(path)]=p.digest(path)
    old=load(p.CONES/'inputs'/scan/'base.npz')
    for arm in p.ARMS:
        path=p.HERE.parent/'2026_10_05_n16_ambiguity_prototypes/polished'/f'{scan}-{arm}-baseline.json'
        source_records.append((f'archive-{arm}',json.loads(path.read_text())['best'],old));sources[str(path)]=p.digest(path)
    for stage in p.STAGES:
        folder=p.HERE/stage/scan;d=load(folder/'position-input.npz')
        meta=json.loads((folder/'position-input.json').read_text())
        for arm in p.ARMS:
            target=folder/'polished'/f'position-{arm}.json'
            if target.exists():
                assert json.loads(target.read_text())['continuation']['sources']==sources
                continue
            original=json.loads((folder/f'position-{arm}.json').read_text())
            obj=p.Objective(d,meta['rf_center_hz'],arm,0.,None,None,None)
            ranked=[]
            for name,seed,old in source_records:
                translated=transfer(seed,old,d);v=p.feasible_start(obj,translated,20.,arm)
                # Explicit receiver bounds also apply to translated warm starts.
                for i,(lo,hi) in enumerate(obj.bounds):
                    if lo is not None:v[i]=max(v[i],lo)
                    if hi is not None:v[i]=min(v[i],hi)
                score,_=obj.evaluate(v);ranked.append((float(score),name,v,seed['point_km']))
            records=[dict(original['best'],stage='original-incumbent')]
            for score,name,v,point in sorted(ranked,key=lambda item:item[0])[:BUDGET['ranked_starts']]:
                r=p.fit(obj,v,point,BUDGET['start_s'],False,radius_km=4.);r['stage']='shared-start-'+name;records.append(r)
            best=min(records,key=lambda r:r['objective'])
            if not p.diagnostics(obj,d,best)['converged']:
                records.append(p.slsqp_fit(obj,best,BUDGET['slsqp_s'],radius_km=4.))
                best=min(records,key=lambda r:r['objective'])
            if not p.diagnostics(obj,d,best)['converged']:
                records.append(p.fit(obj,np.array(best['vector']),best['point_km'],BUDGET['fisher_s'],False,radius_km=4.))
            best=min(records,key=lambda r:r['objective']);metrics=p.diagnostics(obj,d,best)
            assert metrics['objective']<=original['objective']+1e-7
            result=dict(original,**dict(best=best,**metrics))
            result['continuation']=dict(scope=__doc__,sources=sources,budget=BUDGET,records=records,
                implementation_sha256=p.digest(__file__),original_error_m=original['distance_m'],original_objective=original['objective'])
            p.save(target,result)
            print('POLISHED',scan,stage,arm,round(result['distance_m']),result['converged'],flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--workers',type=int,default=3)
    parser.add_argument('--maximum-seconds',type=float,default=2400.)
    args=parser.parse_args();begun=time.monotonic();submitted={}
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        while len(submitted)<len(p.SCANS):
            for scan in p.SCANS:
                if scan not in submitted and all((p.HERE/v/scan/f'position-{a}.json').exists() for v in p.STAGES for a in p.ARMS):
                    submitted[scan]=pool.submit(run,scan)
                if scan in submitted and submitted[scan].done():submitted[scan].result()
            if len(submitted)==len(p.SCANS):break
            if time.monotonic()-begun>args.maximum_seconds:raise TimeoutError('Bounded continuation wait expired')
            time.sleep(10.)
        for future in submitted.values():future.result()
