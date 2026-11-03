"""Matched bounded continuation of saved independent position/nuisance fits.

No observations, priors, likelihood or search disk change. Both RF arms receive
the same source portfolios and budgets. Old fits remain intact. Optional second
optimizer summaries must bind exactly the same inputs; no best-known basin is
discarded merely because a newer optimizer reached a worse one.
"""
import argparse
import inspect
import json
from pathlib import Path

import numpy as np
from cohort import digest
from fisher_position import fit
from position_search import prepare


def best_record(records):
    minimum=min(r['objective'] for r in records)
    near=[r for r in records if r['objective']<=minimum+1e-7]
    # A last-bit numerical tie does not negate an otherwise verified stationary
    # result. Never replace a meaningfully lower score using proximity to truth.
    return min(near,key=lambda r:(not (r['success'] and not r['fixed_location']),r['objective']))


def run(directory,source,additional=None):
    paths=[source]+([additional] if additional else [])
    documents=[json.loads(p.read_text()) for p in paths]
    meta=documents[0]['signature']['inputs']
    if any(d['signature']['inputs']!=meta for d in documents):raise ValueError('optimizer portfolios have different inputs')
    selections=[p for p in meta['sources'] if Path(p).name.startswith('selection-')]
    if len(selections)!=1:raise ValueError('ambiguous association selection')
    data,checked=prepare(directory,meta['method'],meta['ranking'],meta['fraction'],Path(selections[0]).name)
    if checked!=meta:raise ValueError('position input changed')
    from rf_calibration_diagnostic import CalibrationObjective
    from timing_model import TimingObjective
    implementation=[Path(__file__),Path(inspect.getfile(fit)),Path(inspect.getfile(prepare)),
                    Path(inspect.getfile(CalibrationObjective)),Path(inspect.getfile(TimingObjective))]
    signature=dict(inputs=meta,sources={str(p):digest(p.read_bytes()) for p in paths},
                   implementation={str(p):digest(p.read_bytes()) for p in implementation},
                   seed_budget_s=60.,transfer_budget_s=30.,probe_budget_s=8.,scope=__doc__)
    root=directory/'position-polish-v1'/Path(selections[0]).stem/source.parent.name
    root.mkdir(parents=True,exist_ok=True)
    outcomes={}
    for arm in ('fitted-c','zero-c'):
        objective=CalibrationObjective(data,data.initial,np.arange(len(data.numbers)),False,60.)
        objective.base.minimum_shift_s=max(objective.base.minimum_shift_s,-20.)
        objective.base.maximum_shift_s=min(objective.base.maximum_shift_s,20.)
        if arm=='zero-c':objective.bounds[-1]=(0.,0.)
        objective.base.deadline=float('inf')
        records=[dict(r) for d in documents for r in d['arms'][arm]['records']]
        def saved(name,start,point,budget,fixed):
            target=root/f'{arm}-{name}.json'
            if target.exists():
                cache=json.loads(target.read_text())
                if cache['signature']!=signature:raise ValueError('polish cache changed')
                result=cache['result']
            else:
                result=fit(objective,start,point,budget,fixed);result['stage']=name
                with target.open('x') as stream:json.dump(dict(signature=signature,result=result),stream,allow_nan=False)
            records.append(result)
            print('POSITION POLISH',directory.parent.name,arm,name,round(result['objective'],6),result['success'],result['kkt_residual'],flush=True)
            return result
        roof_candidates=[]
        for i,document in enumerate(documents):
            for kind in ('roof','best_found'):
                original=document['arms'][arm][kind]
                vector=np.asarray(original['vector'])
                objective.base.deadline=float('inf')
                if abs(objective.evaluate(vector)[0]-original['objective'])>1e-6:
                    raise ValueError('warm position objective does not reconstruct')
                r=saved(f'seed-{i}-{kind}',vector,original['point_km'],60.,kind=='roof')
                if kind=='roof':roof_candidates.extend((original,r))
        best=best_record(records)
        roof_candidates.append(saved('roof-transfer',best['vector'],[0.,0.],30.,True))
        roof=min(roof_candidates,key=lambda r:r['objective'])
        # Keep both fitted basins in the portfolio; do not reset the best
        # nuisance state to the roof if that produces a worse score.
        saved('joint-from-roof',roof['vector'],best['point_km'],30.,False)
        gradients=[];converged=bool(roof['success'])
        for index,axis in enumerate(np.eye(2)):
            values=[]
            for sign in (-1,1):
                r=saved(f'gradient-{index}-{sign}',roof['vector'],axis*sign*.1,8.,True)
                values.append(r['objective']);converged&=bool(r['success'])
            gradients.append((values[1]-values[0])/.2)
        best=best_record(records)
        joint=[r for r in records if r['success'] and not r['fixed_location']]
        best_joint=best_record(joint) if joint else None
        ambiguous=bool(best_joint and any(np.linalg.norm(np.asarray(r['point_km'])-best_joint['point_km'])>.1
                                           and abs(r['objective']-best_joint['objective'])<1. for r in joint))
        outcomes[arm]=dict(best_found=best,best_converged=best_joint,roof=roof,records=records,
                          radius_m=float(1000*np.linalg.norm(best['point_km'])),boundary=bool(np.linalg.norm(best['point_km'])>1.999),
                          ambiguous=ambiguous,best_found_is_joint_stationary=bool(best['success'] and not best['fixed_location']),
                          finite_difference_gradient={'0.1':dict(gradient_per_km=gradients,all_converged=converged)},
                          claim='Matched additional numerical budget; best of saved basins, not a global certificate.')
    (root/'summary.json').write_text(json.dumps(dict(signature=signature,arms=outcomes),indent=2,allow_nan=False))
    return root/'summary.json'


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);p.add_argument('summary',type=Path)
    p.add_argument('--additional-summary',type=Path)
    a=p.parse_args();run(a.directory,a.summary,a.additional_summary)
