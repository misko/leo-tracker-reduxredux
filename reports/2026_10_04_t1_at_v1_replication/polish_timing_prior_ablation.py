"""Matched cross-prior initializations; no truth-based choice of regularization."""
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import numpy as np
import timing_prior_ablation as experiment
from timing_prior_ablation import load,PriorObjective,PRECISIONS,fit,feasible_start,best_record,diagnostics,serial,digest,reprice

SOURCE=experiment.OUT
OUT=SOURCE/'polished'
BUDGET=dict(each_cross_start=5.,archived_roof_start=8.,polish=6.)


def run(task):
    scan,arm=task;data,meta,_=load(scan)
    paths={m:SOURCE/f'{scan}-{arm}-{m}.json' for m in PRECISIONS}
    originals={m:json.loads(p.read_text()) for m,p in paths.items()}
    archived_path=experiment.SOURCE/scan/f'{arm}-original.json'
    archived=json.loads(archived_path.read_text())
    for mode,precision in PRECISIONS.items():
        target=OUT/paths[mode].name
        if target.exists():continue
        obj=PriorObjective(data,meta['rf_center_hz'],arm,precision)
        original=originals[mode];records=list(original['records'])
        for other in PRECISIONS:
            if other==mode:continue
            seed=reprice(obj,originals[other]['best']);records.append(seed)
            r=fit(obj,feasible_start(obj,seed,20.,arm),seed['point_km'],BUDGET['each_cross_start'],False,radius_km=4.)
            r['stage']=f'cross-start-{other}';records.append(r)
        # Reprofiling the biased MAP minimum at the roof can miss the archived
        # high-likelihood timing branch. Retain this common feasible starting
        # point for EVERY scan/prior/RF arm; select by current objective only.
        seed=reprice(obj,archived['roof']);records.append(seed)
        r=fit(obj,feasible_start(obj,seed,20.,arm),seed['point_km'],BUDGET['archived_roof_start'],False,radius_km=4.)
        r['stage']='archived-roof-joint-start';records.append(r)
        seed=best_record(records)
        r=fit(obj,feasible_start(obj,seed,20.,arm),seed['point_km'],BUDGET['polish'],False,radius_km=4.)
        r['stage']='cross-prior-final-polish';records.append(r)
        best=best_record(records);obj.base.deadline=float('inf');metrics=diagnostics(obj,data,best)
        assert metrics['objective']<=original['objective']+1e-7
        result=dict(original,best=best,records=records,**metrics,polish_scope=__doc__,
            polish_maximum_budgets_s=BUDGET,polish_sources_sha256={m:digest(p) for m,p in paths.items()},
            archived_roof_source_sha256=digest(archived_path),
            polish_implementation_sha256=digest(Path(__file__)))
        target.write_text(json.dumps(result,default=serial,indent=2,allow_nan=False))
        print('POLISHED PRIOR',scan,arm,mode,round(metrics['distance_m']),metrics['converged'],metrics['kkt'],flush=True)


if __name__=='__main__':
    OUT.mkdir(exist_ok=True)
    with ProcessPoolExecutor(max_workers=4) as pool:
        for f in as_completed([pool.submit(run,(s,a)) for s in experiment.SCANS for a in experiment.ARMS]):f.result()
    experiment.OUT=OUT;experiment.render()
