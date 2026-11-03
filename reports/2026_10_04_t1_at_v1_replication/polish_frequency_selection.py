"""Matched final 10 s allowance for all three selection methods and both RF arms."""
import json
from concurrent.futures import ProcessPoolExecutor,as_completed
import numpy as np
from frequency_associations import OUT,PREVIOUS,SCANS,ARMS,MODE
from frequency_localization import read_input
from regularized_localization import read_input as read_previous
from post_scan_tle_localization import make_objective
from convergence_fisher import fit
from resume_position_convergence import best_record
from audit_post_scan_tle import diagnostics
from timing_bound_comparison import digest
from subset_positions import serial

MODES=('count-control','timing-regularized',MODE)


def paths(scan,arm,mode):
    source=OUT/scan/f'{arm}-position.json' if mode==MODE else PREVIOUS/'polished'/scan/f'{arm}-{mode}-position.json'
    target=OUT/'polished'/scan/f'{arm}-{mode}-position.json'
    return source,target


def run(task):
    scan,arm,mode=task;source,target=paths(scan,arm,mode)
    if target.exists():return str(target)
    r=json.loads(source.read_text())
    data,meta=read_input(scan) if mode==MODE else read_previous(scan,mode)
    obj=make_objective(data,meta,arm)
    candidate=fit(obj,np.asarray(r['best']['vector']),r['best']['point_km'],10.,False,radius_km=4.)
    candidate['stage']='final-matched-10s-polish';best=best_record([r['best'],candidate])
    values=diagnostics(obj,data,best)
    assert values['objective']<=r['objective']+1e-7
    result=dict(r,best=best,records=r['records']+[candidate],final_polish_budget_s=10.,
        pre_final_source_sha256=digest(source),**values)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,default=serial,indent=2,allow_nan=False))
    print('FINAL POLISH',scan,arm,mode,round(values['distance_m']),values['converged'],flush=True)
    return str(target)


if __name__=='__main__':
    with ProcessPoolExecutor(max_workers=4) as pool:
        for f in as_completed([pool.submit(run,(s,a,m)) for s in SCANS for a in ARMS for m in MODES]):f.result()
