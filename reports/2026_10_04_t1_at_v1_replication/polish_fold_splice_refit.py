"""Use the latest baseline nuisance mode as an additional matched start.

The older full-calibration runner predates the latest N05 zero-c local mode.
Transfer that mode to every calibration/membership case, then polish equally.
This avoids presenting a known worse control merely because an old runner was
reused. Seeds and winners are chosen by model score, never position truth.
"""
import json
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import numpy as np
import fold_splice_refit as experiment
from fold_splice_refit import SCANS,ARMS,CASES,SOURCE,load,input_data,make_objective,diagnostics,fit,best_record,digest,serial
from full_data_localization import prepare,transferred
from timing_bound_comparison import feasible_start
from audit_regularized_selection import selection_changes

SOURCE_REFITS=experiment.OUT
OUT=SOURCE_REFITS/'polished'
BASELINE=experiment.HERE/'satellite-drift-localization/polished'
EXTRA_BUDGET=dict(latest_control_start=20.,polish=20.)


def run(task):
    scan,case=task
    target=OUT/scan/f'{case}.json';target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():return str(target)
    source=SOURCE_REFITS/scan/f'{case}.json';r=json.loads(source.read_text())
    data,_=input_data(scan,case)
    reconstructed,_,old,_,shifts=prepare(scan,case)
    for field in ('measured','rf','original_rows','numbers','owners'):
        np.testing.assert_array_equal(getattr(data,field),getattr(reconstructed,field))
    seeds={}
    for arm in ARMS:
        previous_path=BASELINE/f'{scan}-{arm}-control.json'
        previous=json.loads(previous_path.read_text())
        seed=transferred(previous['best'],data,old,shifts)
        obj=make_objective(data,r['input_metadata'],arm)
        saved=r['arms'][arm];old_objective=saved['objective']
        trial=fit(obj,feasible_start(obj,seed,20.,arm),seed['point_km'],EXTRA_BUDGET['latest_control_start'],radius_km=4.)
        trial['stage']='latest-control-mode';saved['records'].append(trial)
        best=best_record(saved['records'])
        trial=fit(obj,np.asarray(best['vector']),best['point_km'],EXTRA_BUDGET['polish'],radius_km=4.)
        trial['stage']='latest-control-polish';saved['records'].append(trial)
        saved['best']=best_record(saved['records']);saved.update(diagnostics(obj,data,saved['best']))
        assert saved['objective']<=old_objective+1e-7
        if case=='fold-control':assert saved['objective']<=previous['objective']+1e-7
        seeds[arm]=dict(path=str(previous_path),sha256=digest(previous_path))
        print('COHERENT RX FINAL',scan,case,arm,round(saved['distance_m']),saved['converged'],flush=True)
    r.update(continuation_source_sha256=digest(source),latest_control_seeds=seeds,
             matched_extra_budgets_s=EXTRA_BUDGET,continuation_implementation_sha256=digest(Path(__file__)))
    target.write_text(json.dumps(r,default=serial,indent=2,allow_nan=False))
    return str(target)


def audit():
    changes=[]
    for scan in SCANS:
        _,meta,_=load(scan)
        for case in CASES:
            r=json.loads((OUT/scan/f'{case}.json').read_text())
            assert r['continuation_source_sha256']==digest(SOURCE_REFITS/scan/f'{case}.json')
            assert r['matched_extra_budgets_s']==EXTRA_BUDGET
            assert r['continuation_implementation_sha256']==digest(Path(__file__))
            for arm,seed in r['latest_control_seeds'].items():
                assert seed['sha256']==digest(Path(seed['path']))
                expected=BASELINE/f'{scan}-{arm}-control.json'
                assert Path(seed['path'])==expected
        for arm in ARMS:
            old=json.loads(Path(meta['association_source']).with_name(f'{arm}.json').read_text())
            new=json.loads((SOURCE/scan/'associations'/f'{arm}.json').read_text())
            changes.append(dict(scan=scan,arm=arm,**selection_changes(old,new)))
    # Reuse the numerical/data-inventory audit against the final receipt root.
    # Calibration/input paths are independent of this output-only root.
    experiment.OUT=OUT
    experiment.audit()
    path=OUT/'audit.json';r=json.loads(path.read_text())
    r.update(continuation_scope=__doc__,matched_extra_budgets_s=EXTRA_BUDGET,association_changes=changes)
    path.write_text(json.dumps(r,default=serial,indent=2,allow_nan=False))


if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True)
    with ProcessPoolExecutor(max_workers=4) as pool:
        for f in as_completed([pool.submit(run,(s,c)) for s in SCANS for c in CASES]):f.result()
    audit()
