"""Matched independent 2 km profile/search experiment using Fisher/SQP.

Fixed GLRT membership, same candidate bank, priors, starts and maximum budgets
across RF arms. No earlier position-search vectors are imported. Cross-site
nuisance transfers and repeated profile probes diagnose basin dependence.
"""
import argparse
import inspect
import json
from pathlib import Path

import numpy as np
from cohort import digest
from position_search import prepare,point_design
from fisher_position import fit


LEGACY_WARNING_ONLY_CHANGE={
    'position_search.py':'sha256:4ea8d9db37687994111974af5d1b583cc113cb5bc2f29de19e4bfe6ad132b9e9',
    'run_fisher_positions.py':'sha256:d2b235ea279149dfe78dd68231013d23ad154394fd3101e17171702aaad2b418',
}


def warning_only_cache_compatible(old,current):
    # Exact known revision: the only input-preparation change is an opt-in
    # warning path; strict/default numerical inputs and all budgets are intact.
    # Its original sources are preserved in source-archive. Reuse additionally
    # requires numerical objective reconstruction below, never hashes alone.
    if {k:v for k,v in old.items() if k!='implementation'}!={k:v for k,v in current.items() if k!='implementation'}:
        return False
    if old['implementation'].keys()!=current['implementation'].keys():return False
    return all(value==current['implementation'][path] or LEGACY_WARNING_ONLY_CHANGE.get(Path(path).name)==value
               for path,value in old['implementation'].items())


def run(directory,method='alternatives',ranking='support',fraction=1.,selection='selection-p10-g600-t1.json',smoke=False,permit_calibration_warning=False):
    # All ranking schemes give exactly the same complete observation set.
    # Reuse its single complete-fraction run rather than count it three times.
    if fraction==1.:ranking='support'
    data,meta=prepare(directory,method,ranking,fraction,selection,permit_calibration_warning=permit_calibration_warning)
    from rf_calibration_diagnostic import CalibrationObjective
    from timing_model import TimingObjective
    mean=float(np.mean(data.initial[6:]))
    data.initial[6:]*=min(1.,(10-1e-6)/max(abs(mean),10-1e-6))
    data.initial[6:]=np.clip(data.initial[6:],-20+1e-6,20-1e-6)
    namespace='position-fisher-v2-calibration-warning' if meta.get('calibration_warnings') else 'position-fisher-v2'
    root=directory/namespace/Path(selection).stem/f'{method}-{ranking}-{int(round(fraction*100))}'
    root.mkdir(parents=True,exist_ok=True)
    implementations=[Path(__file__),Path(inspect.getfile(fit)),Path(inspect.getfile(prepare)),
                     Path(inspect.getfile(CalibrationObjective)),Path(inspect.getfile(TimingObjective))]
    signature=dict(inputs=meta,implementation={str(p):digest(p.read_bytes()) for p in implementations},
                   probe_budget_s=8.,search_budget_s=20.,scope=__doc__)
    outcomes={}
    for arm in ('fitted-c','zero-c'):
        objective=CalibrationObjective(data,data.initial,np.arange(len(data.numbers)),False,8.)
        objective.base.minimum_shift_s=max(objective.base.minimum_shift_s,-20.)
        objective.base.maximum_shift_s=min(objective.base.maximum_shift_s,20.)
        if arm=='zero-c':objective.bounds[-1]=(0.,0.)
        initial=objective.initial.copy();initial[-1]=meta['seed_coefficient'] if arm=='fitted-c' else 0.
        records=[]
        def saved_fit(name,start,point,budget,fixed):
            path=root/f'{arm}-{name}.json'
            if path.exists():
                saved=json.loads(path.read_text())
                result=saved['result']
                if saved['signature']!=signature:
                    if not warning_only_cache_compatible(saved['signature'],signature):
                        raise ValueError('Fisher profile cache signature mismatch')
                    objective.base.deadline=float('inf')
                    value,_=objective.evaluate(np.asarray(result['vector']))
                    if abs(value-result['objective'])>1e-6:
                        raise ValueError('legacy cache numerical reconstruction mismatch')
            else:
                result=fit(objective,start,point,budget,fixed)
                result['stage']=name
                with path.open('x') as stream:json.dump(dict(signature=signature,result=result),stream,allow_nan=False)
            records.append(result)
            print('FISHER',directory.parent.name,arm,name,round(result['objective'],3),result['success'],flush=True)
            return result
        roof=saved_fit('roof',initial,[0.,0.],20.,True)
        design=point_design()
        for i,point in enumerate(design[1:3] if smoke else design[1:]):
            saved_fit(f'probe-{i:02d}',roof['vector'],point,8.,True)
        if smoke:continue
        starts=[roof]
        for result in sorted(records,key=lambda r:r['objective']):
            if all(np.linalg.norm(np.asarray(result['point_km'])-other['point_km'])>.4 for other in starts):starts.append(result)
            if len(starts)==3:break
        for i,start in enumerate(starts):saved_fit(f'search-{i}',start['vector'],start['point_km'],20.,False)
        # Transfer nuisance basins in BOTH directions, then optimize position
        # again: fixed-site nuisance convergence alone is not a local minimum.
        for sweep in range(2):
            best=min(records,key=lambda r:r['objective'])
            check=saved_fit(f'roof-transfer-{sweep}',best['vector'],[0.,0.],20.,True)
            roof=min([roof,check],key=lambda r:r['objective'])
            fixed_best=saved_fit(f'best-transfer-{sweep}',roof['vector'],best['point_km'],12.,True)
            saved_fit(f'joint-transfer-{sweep}',fixed_best['vector'],fixed_best['point_km'],20.,False)
        # Re-profile the cardinal points from the best roof nuisance basin.
        finite_differences={}
        for h in (.05,.1):
            pairs=[];all_converged=bool(roof['success'])
            for axis in np.eye(2):
                values=[]
                for sign in (-1,1):
                    r=saved_fit(f'gradient-{h:g}-{int(axis[1])}-{sign}',roof['vector'],axis*sign*h,8.,True)
                    values.append(r['objective']);all_converged&=bool(r['success'])
                pairs.append((values[1]-values[0])/(2*h))
            finite_differences[str(h)]=dict(gradient_per_km=pairs,all_converged=all_converged)
        best=min(records,key=lambda r:r['objective'])
        joint=[r for r in records if r['success'] and not r['fixed_location']]
        best_joint=min(joint,key=lambda r:r['objective']) if joint else None
        ambiguous=bool(best_joint and any(np.linalg.norm(np.asarray(r['point_km'])-best_joint['point_km'])>.1 and
                       abs(r['objective']-best_joint['objective'])<1. for r in joint))
        outcomes[arm]=dict(best_found=best,best_converged=best_joint,roof=roof,records=records,
                           radius_m=float(1000*np.linalg.norm(best['point_km'])),boundary=bool(np.linalg.norm(best['point_km'])>1.999),
                           ambiguous=ambiguous,finite_difference_gradient=finite_differences,
                           best_found_is_joint_stationary=bool(best['success'] and not best['fixed_location']),
                           claim='Best found within disk; local stationary fits and fixed-site convergence distinguished. No global certificate.')
    if not smoke:
        (root/'summary.json').write_text(json.dumps(dict(signature=signature,arms=outcomes),indent=2,allow_nan=False))
    return root


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path)
    p.add_argument('--method',choices=('greedy','replacement','alternatives'),default='alternatives')
    p.add_argument('--ranking',choices=('rms','support','glrt'),default='support');p.add_argument('--fraction',type=float,default=1.)
    p.add_argument('--selection',default='selection-p10-g600-t1.json');p.add_argument('--smoke',action='store_true')
    p.add_argument('--permit-calibration-warning',action='store_true',help='Separate flagged diagnostic namespace; never marks calibration validated')
    a=p.parse_args();run(a.directory,a.method,a.ranking,a.fraction,a.selection,a.smoke,a.permit_calibration_warning)
