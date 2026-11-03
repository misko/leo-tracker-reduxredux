"""One identical extra 20 s maximum refinement for all 64 selection/RF fits."""
import json
from concurrent.futures import ProcessPoolExecutor,as_completed
import numpy as np
from regularized_localization import OUT,SCANS,ARMS,MODES,read_input,make_objective
from convergence_fisher import fit
from resume_position_convergence import best_record
from audit_post_scan_tle import diagnostics
from timing_bound_comparison import digest
from subset_positions import serial


def run(task):
    scan,arm,mode=task;name=f'{arm}-{mode}-position.json'
    source=OUT/scan/name;target=OUT/'polished'/scan/name
    if target.exists():return str(target)
    r=json.loads(source.read_text());d,meta=read_input(scan,mode);obj=make_objective(d,meta,arm)
    candidate=fit(obj,np.asarray(r['best']['vector']),r['best']['point_km'],20.,False,radius_km=4.)
    candidate['stage']='matched-extra-polish'
    best=best_record([r['best'],candidate]);values=diagnostics(obj,d,best)
    assert values['objective']<=r['objective']+1e-7
    result=dict(r,best=best,records=r['records']+[candidate],extra_polish_budget_s=20.,
        pre_polish_receipt_sha256=digest(source),**values)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,default=serial,indent=2,allow_nan=False))
    print('POLISHED',scan,arm,mode,round(values['distance_m']),values['converged'],flush=True)
    return str(target)


if __name__=='__main__':
    with ProcessPoolExecutor(max_workers=4) as pool:
        for f in as_completed([pool.submit(run,(s,a,m)) for s in SCANS for a in ARMS for m in MODES]):f.result()
