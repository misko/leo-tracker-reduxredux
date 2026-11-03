"""Bounded optimizer-only N05 continuation, matched across all six variants."""
import json
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import numpy as np
import timing_prior_ablation as experiment
from timing_prior_ablation import PriorObjective,load,fit,diagnostics,best_record,digest,serial

SOURCE=experiment.OUT/'polished'
OUT=experiment.OUT/'final'
BUDGET_S=30.


def run(task):
    arm,mode=task;source=SOURCE/f'N05-{arm}-{mode}.json';target=OUT/source.name
    if target.exists():return str(target)
    original=json.loads(source.read_text());d,m,_=load('N05')
    obj=PriorObjective(d,m['rf_center_hz'],arm,experiment.PRECISIONS[mode]);seed=original['best']
    r=fit(obj,np.asarray(seed['vector']),seed['point_km'],BUDGET_S,False,radius_km=4.)
    r['stage']='matched-N05-30s-continuation';records=original['records']+[r];best=best_record(records)
    obj.base.deadline=float('inf');metrics=diagnostics(obj,d,best)
    result=dict(original,best=best,records=records,**metrics,continuation_maximum_budget_s=BUDGET_S,
                continuation_source_sha256=digest(source),continuation_implementation_sha256=digest(Path(__file__)))
    assert metrics['objective']<=original['objective']+1e-7
    target.write_text(json.dumps(result,default=serial,indent=2,allow_nan=False))
    print('N05 CONTINUED',arm,mode,round(metrics['distance_m']),metrics['converged'],metrics['kkt'],r['status'],flush=True)


if __name__=='__main__':
    OUT.mkdir(exist_ok=True)
    # Immutable copies, preserving every earlier fit and its provenance.
    for path in SOURCE.glob('N*.json'):
        if not path.name.startswith('N05-'):
            target=OUT/path.name
            if not target.exists():target.write_bytes(path.read_bytes())
            assert target.read_bytes()==path.read_bytes()
    with ProcessPoolExecutor(max_workers=4) as pool:
        for f in as_completed([pool.submit(run,(a,m)) for a in experiment.ARMS for m in experiment.PRECISIONS]):f.result()
    experiment.OUT=OUT;experiment.render()
