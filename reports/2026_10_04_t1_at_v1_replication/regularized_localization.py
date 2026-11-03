"""Independent localization after timing-regularized association selection.

No truth-selected satellite deletion: one fixed selection rule across N01--N16.
Each RF pair uses the same fitted-c-selected windows and satellite bank. Refit
all retained windows, original timing priors/bounds, archived RX baseline/TLEs.
The count control exactly reproduces the old localization inputs. Candidate
selection changes the data/bank, so absolute NLL is not comparable across cases.
"""
import argparse
import copy
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from regularized_associations import OUT, INPUTS, SCANS, ARMS, MODES
from run import HERE, TopAbsoluteCalibration
from full_data_localization import fold_baseline
from leave_one_satellite_out import load
from post_scan_tle_localization import make_objective
from convergence_fisher import fit
from resume_position_convergence import best_record
from timing_bound_comparison import feasible_start, digest
from subset_positions import serial
from audit_post_scan_tle import diagnostics

FIELDS = ('times','measured','rf','receiver','channel','group','margin','original_rows',
          'owners','numbers','position','velocity','nodes','initial','fixed_receiver_hz')
BUDGET = dict(roof=6., probe=.5, search=8., polish=8.)
SOURCE = HERE/'timing-prior-ablation/closed'


def select_input(raw, baseline, receipt):
    assignments = sorted(receipt['final']['assignments'], key=lambda a:a['row_index'])
    lookup = {int(r):i for i,r in enumerate(raw.original_rows)}
    rows = np.array([lookup[a['row_index']] for a in assignments], int)
    if len(rows) != len(set(rows)):raise ValueError('Duplicate associated window')
    selected = {int(a['catalog_number']):a for a in receipt['final']['selected']}
    numbers = sorted(selected)
    columns = np.array([int(np.flatnonzero(raw.numbers == n)[0]) for n in numbers])
    data = copy.copy(raw)
    for key in ('times','measured','rf','receiver','channel','group','margin','original_rows'):
        setattr(data,key,getattr(raw,key)[rows].copy())
    data.fixed_receiver_hz = np.asarray(baseline)[rows].copy()
    data.measured -= data.fixed_receiver_hz
    data.owners = np.array([a['catalog_number'] for a in assignments])
    data.numbers = raw.numbers[columns]
    data.position, data.velocity = raw.position[columns], raw.velocity[columns]
    data.initial = np.r_[raw.initial[:2], np.zeros(4), [selected[n]['offset_s'] for n in numbers]]
    if not set(data.owners) <= set(data.numbers):raise ValueError('Owner outside candidate bank')
    return data


def remap_seed(record, old_numbers, data):
    parameters = np.asarray(record['parameters'])
    timing = dict(zip(map(int,old_numbers), parameters[6:]))
    p = np.r_[parameters[:6], [timing.get(int(n),data.initial[6+i]) for i,n in enumerate(data.numbers)]]
    return dict(record, parameters=p)


def prepare(scan):
    cal = TopAbsoluteCalibration(INPUTS/scan/'seed-timing-v6')
    cal.data.label = scan
    baseline, coefficient = fold_baseline(cal)
    old, old_meta, _ = load(scan)
    for mode in MODES:
        source = OUT/scan/f'fitted-c-{mode}.json'
        receipt = json.loads(source.read_text())
        data = select_input(cal.data, baseline, receipt)
        if mode == 'count-control':
            for key in FIELDS:
                np.testing.assert_allclose(getattr(data,key),getattr(old,key),atol=1e-7,rtol=0,err_msg=key)
        target = OUT/scan/f'{mode}-input.npz'
        if not target.exists():np.savez_compressed(target,**{k:getattr(data,k) for k in FIELDS})
        with np.load(target) as saved:
            for key in FIELDS:np.testing.assert_array_equal(saved[key],getattr(data,key))
        metadata = dict(scan=scan, mode=mode, input_sha256=digest(target),
            association_source=str(source), association_sha256=digest(source),
            seed_coefficient=coefficient, rf_center_hz=old_meta['rf_center_hz'],
            raw_sources=cal.data.sources, sources=cal.sources,
            original_rows=data.original_rows, numbers=data.numbers, owners=data.owners,
            full_top_window_denominator=len(cal.data.times), windows=len(data.times),
            scope=__doc__, heldout_original_rows=[],
            upstream_calibration='Existing archived fold-derived receiver baseline unchanged.',
            control_input_reproduced=mode=='count-control')
        target.with_suffix('.json').write_text(json.dumps(metadata,default=serial,indent=2,allow_nan=False))
    return scan


def read_input(scan, mode):
    source=OUT/scan/f'{mode}-input.npz'
    meta=json.loads(source.with_suffix('.json').read_text())
    assert digest(source)==meta['input_sha256']
    with np.load(source) as z:data=SimpleNamespace(**{k:z[k].copy() for k in z.files})
    return data,meta


def run(task):
    scan, arm, mode = task
    target = OUT/scan/f'{arm}-{mode}-position.json'
    if target.exists():return str(target)
    data,meta=read_input(scan,mode)
    old,_,older=load(scan)
    source=SOURCE/f'{scan}-{arm}-original.json'
    previous=json.loads(source.read_text())
    seeds=[remap_seed(r,old.numbers,data) for r in (older['arms'][arm]['roof'],previous['best'])]
    association_seed=dict(parameters=data.initial,coefficient=meta['seed_coefficient'],point_km=[0.,0.])
    obj=make_objective(data,meta,arm);records=[]
    def fitted(stage,seed,point,budget,fixed=False):
        r=fit(obj,feasible_start(obj,seed,20.,arm),point,budget,fixed,radius_km=4.)
        r['stage']=stage;records.append(r);return r
    # Include both historical nuisance basins and the newly selected timing.
    roofs=[fitted(f'roof-{i}',seed,[0.,0.],BUDGET['roof'],True)
           for i,seed in enumerate([seeds[0],seeds[1],association_seed])]
    roof=min(roofs,key=lambda r:r['objective'])
    probes=[]
    for i,angle in enumerate(np.arange(4)*np.pi/2):
        point=3.2*np.array([np.cos(angle),np.sin(angle)])
        probes.append(fitted(f'probe-{i}',roof,point,BUDGET['probe'],True))
    starts=[roof,seeds[1],min(probes,key=lambda r:r['objective'])]
    for i,seed in enumerate(starts):
        fitted(f'search-{i}',seed,seed['point_km'],BUDGET['search'])
    best=best_record(records)
    fitted('polish',best,best['point_km'],BUDGET['polish'])
    best=best_record(records)
    values=diagnostics(obj,data,best)
    assert abs(values['objective']-best['objective'])<1e-7
    assert np.linalg.norm(best['point_km'])<=4.+1e-7
    assert np.max(abs(np.asarray(best['parameters'])[6:]))<=20.+1e-7
    result=dict(scope=__doc__,scan=scan,arm=arm,mode=mode,
        input_sha256=meta['input_sha256'],source_sha256=digest(source),
        implementation_sha256=digest(Path(__file__)),fit_original_rows=data.original_rows,
        evaluation_original_rows=data.original_rows,heldout_original_rows=[],
        numbers=data.numbers,windows=len(data.times),denominator=meta['full_top_window_denominator'],
        maximum_budgets_s=BUDGET,roof_starts=3,spatial_starts=3,
        radius_km=4.,total_timing_bound_s=20.,best=best,roof=roof,records=records,**values)
    target.write_text(json.dumps(result,default=serial,indent=2,allow_nan=False))
    print('REGULARIZED POSITION',scan,arm,mode,round(values['distance_m']),values['converged'],best['status'],flush=True)
    return str(target)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--prepare-only',action='store_true')
    parser.add_argument('--scans',nargs='+',default=SCANS,choices=SCANS)
    args=parser.parse_args()
    with ProcessPoolExecutor(max_workers=4) as pool:
        for f in as_completed([pool.submit(prepare,s) for s in args.scans]):
            print('INPUT READY',f.result(),flush=True)
    if not args.prepare_only:
        tasks=[(s,a,m) for s in args.scans for a in ARMS for m in MODES]
        with ProcessPoolExecutor(max_workers=4) as pool:
            for f in as_completed([pool.submit(run,t) for t in tasks]):f.result()
