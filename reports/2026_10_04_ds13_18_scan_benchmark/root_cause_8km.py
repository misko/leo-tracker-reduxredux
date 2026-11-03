"""Independent 8 km searches with frozen observations/priors and paired RF arms.

Explicit post-hoc diagnostic extension, separate from the locked 2 km study.
24 common area/boundary probes, common multistart coordinates in both RF arms,
and nuisance transfers. Convergence is audited; no global-optimum certificate.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import inspect
import json
from pathlib import Path
import time
import numpy as np
from cohort import digest
from root_cause import LABELS, ARMS, load_case, make_objective
from radius_fisher import fit


def design(seed=20261004):
    rng=np.random.default_rng(seed)
    points=[]
    for radius in (4.,8.):
        for angle in np.arange(8)*np.pi/4:
            points.append([radius*np.cos(angle),radius*np.sin(angle)])
    for sector in range(8):
        angle=rng.uniform(sector*np.pi/4,(sector+1)*np.pi/4)
        radius=np.sqrt(rng.uniform(4.,64.))
        points.append([radius*np.cos(angle),radius*np.sin(angle)])
    return np.array(points)


def choose_starts(old,records):
    points=[np.zeros(2)]
    candidates=[old['arms'][arm]['best_found']['point_km'] for arm in ARMS]
    for arm in ARMS:
        candidates.extend(r['point_km'] for r in sorted(records[arm],key=lambda r:r['objective']))
    for candidate in candidates:
        point=np.asarray(candidate)
        if all(np.linalg.norm(point-other)>1. for other in points):points.append(point)
        if len(points)==5:break
    return points


def run_scan(task):
    root,output,label=task
    data,meta,owners,old,source,sha=load_case(root,label)
    folder=Path(output)/label;folder.mkdir(parents=True,exist_ok=True)
    signature=dict(source=source,source_sha256=sha,radius_km=8.,
        fixed_probe_budget_s=4.,roof_budget_s=20.,search_budget_s=20.,
        implementation={str(p):digest(p.read_bytes()) for p in [Path(__file__),Path(inspect.getfile(fit))]},
        scope=__doc__)
    summary=folder/'summary.json'
    if summary.exists():
        if json.loads(summary.read_text())['signature']!=signature:raise ValueError('8km summary signature mismatch')
        return str(summary)
    center=float(np.mean(np.unique(data.rf)))
    objectives={arm:make_objective(data,center,arm) for arm in ARMS}
    records={arm:[] for arm in ARMS}
    roofs={}
    def saved_fit(arm,name,start,point,budget,fixed):
        path=folder/f'{arm}-{name}.json'
        if path.exists():
            doc=json.loads(path.read_text())
            if doc['signature']!=signature:raise ValueError('8km fit signature mismatch')
            record=doc['result']
        else:
            record=fit(objectives[arm],start,point,budget,fixed,radius_km=8.)
            record['stage']=name
            with path.open('x') as stream:json.dump(dict(signature=signature,result=record),stream,allow_nan=False)
        records[arm].append(record)
        return record
    for arm in ARMS:
        obj=objectives[arm];obj.base.deadline=float('inf')
        for key in ('roof','best_found'):
            record=old['arms'][arm][key]
            value,_=obj.evaluate(np.asarray(record['vector']))
            if abs(value-record['objective'])>1e-6:raise ValueError('old objective reconstruction failed')
        roofs[arm]=saved_fit(arm,'roof',old['arms'][arm]['roof']['vector'],[0.,0.],20.,True)
        # All RF arms receive the exact same probe coordinates.
        for i,point in enumerate(design()):
            nearest=min([roofs[arm],old['arms'][arm]['best_found']],key=lambda r:np.linalg.norm(point-r['point_km']))
            saved_fit(arm,f'probe-{i:02d}',nearest['vector'],point,4.,True)
    starts=choose_starts(old,records)
    outcomes={}
    for arm in ARMS:
        for i,point in enumerate(starts):
            nearest=min(records[arm]+[old['arms'][arm]['best_found']],key=lambda r:np.linalg.norm(point-r['point_km']))
            saved_fit(arm,f'search-{i}',nearest['vector'],point,20.,False)
        for sweep in range(2):
            best=min(records[arm]+[old['arms'][arm]['best_found']],key=lambda r:r['objective'])
            check=saved_fit(arm,f'roof-transfer-{sweep}',best['vector'],[0.,0.],12.,True)
            roofs[arm]=min([roofs[arm],check],key=lambda r:r['objective'])
            saved_fit(arm,f'joint-transfer-{sweep}',best['vector'],best['point_km'],20.,False)
        best=min(records[arm]+[old['arms'][arm]['best_found']],key=lambda r:r['objective'])
        radius=float(np.linalg.norm(best['point_km'])*1000)
        converged=[r for r in records[arm] if r['success'] and not r['fixed_location']]
        stationary=bool(any(abs(r['objective']-best['objective'])<1e-6 and np.linalg.norm(np.array(r['point_km'])-best['point_km'])<1e-3 for r in converged))
        outcomes[arm]=dict(best=best,roof=roofs[arm],radius_m=radius,
            best_is_joint_stationary=stationary,boundary=radius>=7999.,
            best_minus_roof_nll=best['objective']-roofs[arm]['objective'],
            best_minus_original_2km_nll=best['objective']-old['arms'][arm]['best_found']['objective'],
            original_2km_error_m=old['arms'][arm]['radius_m'],
            calibration_warning=bool(meta.get('calibration_warnings')),
            converged_joint_solutions=len(converged),
            distinct_competing_minima=[dict(point_km=r['point_km'],objective=r['objective']) for r in converged if np.linalg.norm(np.array(r['point_km'])-best['point_km'])>.1 and abs(r['objective']-best['objective'])<1.],
            records=records[arm])
        print('8KM',label,arm,round(radius),best['status'],'stationary',stationary,flush=True)
    summary.write_text(json.dumps(dict(signature=signature,scan=label,common_starts_km=[p.tolist() for p in starts],arms=outcomes),indent=2,allow_nan=False))
    return str(summary)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root');p.add_argument('output')
    p.add_argument('--labels',nargs='+',default=LABELS);p.add_argument('--workers',type=int,default=12)
    a=p.parse_args()
    if not 1<=a.workers<=14:raise ValueError('bounded workers required')
    priority=['N15','B','N05','N06','N12','N16','N07','N10']
    labels=sorted(a.labels,key=lambda label:priority.index(label) if label in priority else 99)
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        futures=[pool.submit(run_scan,(a.root,a.output,label)) for label in labels]
        for future in as_completed(futures):print('COMPLETE',future.result(),flush=True)
