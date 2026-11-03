"""One bounded paired-RF convergence retry for the saved 8 km diagnostic."""
import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
import json
from pathlib import Path
import numpy as np
from cohort import digest
from root_cause import load_case,make_objective,ARMS
from radius_fisher import fit


def run(task):
    root,source,output,label=task
    path=Path(source)/label/'summary.json';saved=json.loads(path.read_text())
    folder=Path(output)/label;folder.mkdir(parents=True,exist_ok=True)
    data,meta,_,_,_,_=load_case(root,label)
    signature=dict(source_sha256=digest(path.read_bytes()),implementation=digest(Path(__file__).read_bytes()),
        budget_per_arm_s=150.,scope=__doc__)
    target=folder/'summary.json'
    if target.exists():
        if json.loads(target.read_text())['polish_signature']!=signature:raise ValueError('polish cache mismatch')
        return label
    result=json.loads(path.read_text());result['polish_signature']=signature
    for arm in ARMS:
        obj=make_objective(data,float(np.mean(np.unique(data.rf))),arm)
        old=saved['arms'][arm]
        records=list(old['records'])
        def step(name,start,point,budget,fixed):
            dest=folder/f'{arm}-{name}.json'
            if dest.exists():
                doc=json.loads(dest.read_text())
                if doc['signature']!=signature:raise ValueError('polish step signature mismatch')
                r=doc['result']
            else:
                r=fit(obj,start,point,budget,fixed,radius_km=8.);r['stage']=name
                with dest.open('x') as stream:json.dump(dict(signature=signature,result=r),stream,allow_nan=False)
            records.append(r);return r
        roof=step('polish-roof',old['roof']['vector'],[0.,0.],30.,True)
        near=step('polish-near',roof['vector'],[0.,0.],45.,False)
        far=step('polish-far',old['best']['vector'],old['best']['point_km'],45.,False)
        best=min([old['best'],near,far],key=lambda r:r['objective'])
        transferred=step('polish-roof-transfer',best['vector'],[0.,0.],30.,True)
        roof=min([roof,old['roof'],transferred],key=lambda r:r['objective'])
        # The final fixed-site transfer can uncover a lower nuisance basin.
        # Do not label an inferior converged joint endpoint as the best result.
        best=min([old['best'],*records],key=lambda r:r['objective'])
        converged=[r for r in records if r['success'] and not r['fixed_location']]
        stationary=any(abs(r['objective']-best['objective'])<1e-6 and np.linalg.norm(np.array(r['point_km'])-best['point_km'])<1e-3 for r in converged)
        new=result['arms'][arm];new.update(best=best,roof=roof,records=records,
            radius_m=float(np.linalg.norm(best['point_km'])*1000),
            best_is_joint_stationary=bool(stationary),boundary=bool(np.linalg.norm(best['point_km'])>=7.999),
            best_minus_roof_nll=best['objective']-roof['objective'],
            best_minus_original_2km_nll=old['best_minus_original_2km_nll']+best['objective']-old['best']['objective'],
            converged_joint_solutions=len(converged),
            distinct_competing_minima=[dict(point_km=r['point_km'],objective=r['objective']) for r in converged if np.linalg.norm(np.array(r['point_km'])-best['point_km'])>.1 and abs(r['objective']-best['objective'])<1.])
        print('POLISH8',label,arm,round(new['radius_m']),best['status'],stationary,flush=True)
    target.write_text(json.dumps(result,indent=2,allow_nan=False))
    return label


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root');p.add_argument('source');p.add_argument('output');p.add_argument('--labels',nargs='+',required=True);p.add_argument('--workers',type=int,default=6)
    a=p.parse_args()
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        for future in as_completed([pool.submit(run,(a.root,a.source,a.output,label)) for label in a.labels]):print('POLISHED',future.result(),flush=True)
