"""Matched independent 4 km refits for frequency-regularized satellite selection.

All selected top-one windows enter every fit; no new folds or truth-position prior.
Fitted-c selection anchors both RF arms. Original RX/TLE calibration, finite-set
NLL and timing priors unchanged. Search budgets/starts match the saved count
control in timing-regularized-selection/polished, including the extra 20 s polish.
"""
import json
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from frequency_associations import OUT,PREVIOUS,INPUTS,SCANS,ARMS,HERE,MODE
from regularized_localization import FIELDS,BUDGET,SOURCE,select_input,remap_seed,read_input as read_control
from run import TopAbsoluteCalibration
from full_data_localization import fold_baseline
from leave_one_satellite_out import load
from post_scan_tle_localization import make_objective
from convergence_fisher import fit
from resume_position_convergence import best_record
from timing_bound_comparison import feasible_start,digest
from subset_positions import serial
from audit_post_scan_tle import diagnostics


def prepare(scan):
    cal=TopAbsoluteCalibration(INPUTS/scan/'seed-timing-v6');cal.data.label=scan
    baseline,coefficient=fold_baseline(cal)
    control,control_meta=read_control(scan,'count-control')
    expected=select_input(cal.data,baseline,json.loads((PREVIOUS/scan/'fitted-c-count-control.json').read_text()))
    for k in FIELDS:np.testing.assert_array_equal(getattr(expected,k),getattr(control,k))
    source=OUT/scan/'fitted-c.json';receipt=json.loads(source.read_text())
    data=select_input(cal.data,baseline,receipt);target=OUT/scan/'input.npz'
    if not target.exists():np.savez_compressed(target,**{k:getattr(data,k) for k in FIELDS})
    with np.load(target) as z:
        for k in FIELDS:np.testing.assert_array_equal(z[k],getattr(data,k))
    meta=dict(scan=scan,mode=MODE,input_sha256=digest(target),association_source=str(source),association_sha256=digest(source),
        control_input_sha256=control_meta['input_sha256'],control_input_reproduced=True,
        raw_sources=cal.data.sources,sources=cal.sources,rf_center_hz=control_meta['rf_center_hz'],
        seed_coefficient=coefficient,original_rows=data.original_rows,numbers=data.numbers,owners=data.owners,
        windows=len(data.times),full_top_window_denominator=len(cal.data.times),heldout_original_rows=[],scope=__doc__)
    target.with_suffix('.json').write_text(json.dumps(meta,default=serial,indent=2,allow_nan=False))
    return scan


def read_input(scan):
    source=OUT/scan/'input.npz';meta=json.loads(source.with_suffix('.json').read_text())
    assert digest(source)==meta['input_sha256']
    with np.load(source) as z:data=SimpleNamespace(**{k:z[k].copy() for k in z.files})
    return data,meta


def run(task):
    scan,arm=task;target=OUT/scan/f'{arm}-position.json'
    if target.exists():return str(target)
    data,meta=read_input(scan);old,_,older=load(scan)
    source=SOURCE/f'{scan}-{arm}-original.json';previous=json.loads(source.read_text())
    seeds=[remap_seed(r,old.numbers,data) for r in (older['arms'][arm]['roof'],previous['best'])]
    association_seed=dict(parameters=data.initial,coefficient=meta['seed_coefficient'],point_km=[0.,0.])
    obj=make_objective(data,meta,arm);records=[]
    def fitted(stage,seed,point,budget,fixed=False):
        r=fit(obj,feasible_start(obj,seed,20.,arm),point,budget,fixed,radius_km=4.)
        r['stage']=stage;records.append(r);return r
    roofs=[fitted(f'roof-{i}',seed,[0.,0.],BUDGET['roof'],True)
        for i,seed in enumerate([seeds[0],seeds[1],association_seed])]
    roof=min(roofs,key=lambda r:r['objective']);probes=[]
    for i,angle in enumerate(np.arange(4)*np.pi/2):
        point=3.2*np.array([np.cos(angle),np.sin(angle)])
        probes.append(fitted(f'probe-{i}',roof,point,BUDGET['probe'],True))
    for i,seed in enumerate([roof,seeds[1],min(probes,key=lambda r:r['objective'])]):
        fitted(f'search-{i}',seed,seed['point_km'],BUDGET['search'])
    best=best_record(records);fitted('polish',best,best['point_km'],BUDGET['polish'])
    best=best_record(records);fitted('matched-extra-polish',best,best['point_km'],20.)
    best=best_record(records);values=diagnostics(obj,data,best)
    assert abs(values['objective']-best['objective'])<1e-7
    assert np.linalg.norm(best['point_km'])<=4.+1e-7
    assert np.max(abs(np.asarray(best['parameters'])[6:]))<=20.+1e-7
    r=dict(scope=__doc__,scan=scan,arm=arm,mode=MODE,
        input_sha256=meta['input_sha256'],source_sha256=digest(source),
        implementation_sha256=digest(Path(__file__)),fit_original_rows=data.original_rows,
        evaluation_original_rows=data.original_rows,heldout_original_rows=[],
        numbers=data.numbers,windows=len(data.times),denominator=meta['full_top_window_denominator'],
        maximum_budgets_s=BUDGET,extra_polish_budget_s=20.,roof_starts=3,spatial_starts=3,
        radius_km=4.,total_timing_bound_s=20.,best=best,roof=roof,records=records,**values)
    target.write_text(json.dumps(r,default=serial,indent=2,allow_nan=False))
    print('FREQUENCY POSITION',scan,arm,round(values['distance_m']),values['converged'],best['status'],flush=True)
    return str(target)


if __name__=='__main__':
    with ProcessPoolExecutor(max_workers=4) as pool:
        for f in as_completed([pool.submit(prepare,s) for s in SCANS]):print('INPUT READY',f.result(),flush=True)
    with ProcessPoolExecutor(max_workers=4) as pool:
        for f in as_completed([pool.submit(run,(s,a)) for s in SCANS for a in ARMS]):f.result()
