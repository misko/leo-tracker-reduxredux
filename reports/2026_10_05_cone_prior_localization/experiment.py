"""Four cone-prior variants on N01--N16, independent matched 4 km searches.

Exploratory in-sample known-roof analysis, not blind validation. Freeze the
20-scan cone fit, full-data frequency calibration, GLRT refinement, timing-mode
pool and ordinary C1 likelihood. No IQ recomputation or new RF collection.
Selection uses positive-receiver marginal evidence only, no invented peer
non-detections. RF arms share the fitted-c-selected observations and bank.
"""
import argparse
import copy
import hashlib
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

import numpy as np

HERE = Path(__file__).resolve().parent
BASE = HERE.parent/'2026_10_04_t1_at_v1_replication'
CONES = HERE.parent/'2026_10_05_receiver_cones'
sys.path[:0] = [str(HERE), str(BASE), str(CONES)]
import full_data_calibration as calibration
from numeric_data import enable_research_model
enable_research_model()
sys.path.insert(0, str(calibration.LEGACY))
import greedy_pool_two_scans as historical
sys.path.insert(0, str(historical.OLD))
from greedy_restart_scan import compile_mode
from cone_model import frame, BORESIGHTS_DEG
from receiver_sky_model import prepare as prepare_sky
from cone_geometry import Support
from cone_objective import Objective
from cone_selection import ConeSearch, add_evidence
from convergence_fisher import fit
from position_structure_study import reprice, seed_vector
from audit_post_scan_tle import diagnostics
from full_data_timing_priors import load as load_previous
from subset_positions import serial

SCANS = tuple(f'N{i:02}' for i in range(1, 17))
ARMS = ('fitted-c', 'zero-c')
VARIANTS = {'control': (0., 0.), 'selection': (1., 0.),
            'position': (0., .5), 'combined': (1., .5)}
BUDGET = dict(roof_s=2., search_starts=3, search_s=4., polish_s=8., cross_s=5.)
CAL = BASE/'full-scan-seed-restart'
FIELDS = ('times','measured','rf','receiver','channel','group','margin','original_rows',
          'owners','numbers','position','velocity','nodes','initial','fixed_receiver_hz')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@lru_cache(maxsize=1)
def bundle():
    summary = json.loads((CONES/'summary.json').read_text())
    records = []
    for name, sha in summary['sources'].items():
        assert digest(name)==sha
        records.extend(e for e in json.loads(Path(name).read_text())['events']
                       if e['arm']=='fitted-c' and e['gate_hz']==600)
    d = prepare_sky(records)
    outcome = np.bincount(d['outcome'], weights=d['weight'], minlength=3)/d['weight'].sum()
    null = np.array([outcome[0]+outcome[2], outcome[1]+outcome[2]])
    with np.load(CONES/'sky-maps.npz') as z:
        support = Support(z['inside'], z['supported'])
    return np.array(summary['primary']['theta']), np.array([frame(*a) for a in BORESIGHTS_DEG]), support, null


def save(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, default=serial, indent=2, allow_nan=False))


def signatures():
    files = ['experiment.py','cone_geometry.py','cone_objective.py','cone_selection.py']
    return {str(HERE/f): digest(HERE/f) for f in files} | {
        str(CONES/f): digest(CONES/f) for f in ['cone_model.py','summary.json','sky-maps.npz']}


def prepare_scan(scan):
    started = time.monotonic()
    folder = HERE/'inputs'/scan
    receipt = folder/'receipt.json'
    if receipt.exists():
        r = json.loads(receipt.read_text())
        assert r['dependencies']==signatures()
        for path, sha in r['sources'].items():
            assert digest(path)==sha
        return r
    theta, frames, support, null = bundle()
    calibration.OUT = CAL
    cal = calibration.FullCalibration(scan)
    raw = cal.data
    path = CAL/scan/'associations/candidate-pool.json'
    pool = json.loads(path.read_text())
    assert pool['calibration_sha256'].removeprefix('sha256:')==digest(cal.path)
    assert pool['original_rows']==raw.original_rows.tolist()
    records = pool['arms']['fitted-c']
    modes = [compile_mode(m, raw.receiver, raw.channel) for m in records]
    add_evidence(modes, records, raw, theta, frames, support, null)
    reference_path = CAL/scan/'associations/fitted-c.json'
    reference = json.loads(reference_path.read_text())
    old, previous, _ = load_previous(scan)
    sources = {str(path):digest(path),str(cal.path):digest(cal.path),str(reference_path):digest(reference_path)}
    sources.update({p:h.removeprefix('sha256:') for p,h in raw.sources.items()})
    # Both frozen historical RF-start pools are provided to every new case.
    archived = [dict(previous['arms'][a]['best'], source_numbers=old.numbers.tolist()) for a in ARMS]
    for arm in ARMS:
        path = BASE/'position-visibility-study/polished'/f'{scan}-{arm}-ordinary-Q1.json'
        if path.exists():
            record = json.loads(path.read_text())
            assert record['numbers']==old.numbers.tolist()
            archived.append(dict(record['best'], source_numbers=record['numbers']))
            sources[str(path)] = digest(path)
    selections = {}; metadata = {}
    for label, strength in [('base',0.),('sky',1.)]:
        result = ConeSearch(modes, raw.group, raw.times, strength=strength).run(3)
        # Check exact zero-strength parity with the saved full-data baseline.
        for stage in ('initial','final'):
            for a in result[stage]['assignments']:
                a['row_index'] = int(raw.original_rows[a['row_index']])
            if not strength:
                for name in ('assigned','satellites','objective','assignments','selected'):
                    assert result[stage][name]==reference[stage][name], (scan,stage,name)
        if not strength:
            assert result['passes']==reference['passes']
        final = result['final']
        assigned = sorted(final['assignments'], key=lambda a:a['row_index'])
        lookup = {int(v):i for i,v in enumerate(raw.original_rows)}
        rows = np.array([lookup[a['row_index']] for a in assigned])
        selected = {a['catalog_number']:a for a in final['selected']}
        numbers = sorted(selected)
        columns = np.array([np.flatnonzero(raw.numbers==n)[0] for n in numbers])
        d = copy.copy(raw)
        for field in FIELDS[:8]:
            setattr(d, field, getattr(raw, field)[rows].copy())
        baseline = cal.receiver_baseline('fitted-c')[rows]
        d.measured -= baseline; d.fixed_receiver_hz = baseline
        d.owners = np.array([a['catalog_number'] for a in assigned])
        d.numbers = raw.numbers[columns]; d.position = raw.position[columns]; d.velocity = raw.velocity[columns]
        d.initial = np.r_[raw.initial[:2], np.zeros(4), [selected[n]['offset_s'] for n in numbers]]
        if label=='base':
            for field in FIELDS:
                np.testing.assert_allclose(getattr(d,field),getattr(old,field),rtol=0,atol=1e-9,err_msg=field)
        folder.mkdir(parents=True,exist_ok=True)
        target = folder/f'{label}.npz'
        np.savez_compressed(target, **{k:getattr(d,k) for k in FIELDS})
        final.update(denominator=len(raw.times),coverage=len(rows)/len(raw.times))
        result.update(scan=scan,strength=strength,prior='positive RX marginal; mean log odds per satellite/5s; clipped +/-3')
        save(folder/f'{label}-selection.json',result)
        selections[label] = result
        metadata[label] = dict(input_sha256=digest(target),windows=len(rows),satellites=len(numbers),
            numbers=numbers,original_rows=d.original_rows.tolist(),coverage=final['coverage'],
            selection_score=final['objective'],replacement_converged=result['converged'],
            rms_hz=float(np.sqrt(np.mean([a['residual_hz']**2 for a in assigned]))))
    base = {a['row_index']:a['catalog_number'] for a in selections['base']['final']['assignments']}
    sky = {a['row_index']:a['catalog_number'] for a in selections['sky']['final']['assignments']}
    result = dict(scan=scan,dependencies=signatures(),sources=sources,inputs=metadata,
        rf_center_hz=cal.record['rf_center_hz'],seed_records=archived,
        calibration_coefficient=cal.record['arms']['fitted-c']['coefficient'],
        lost=len(base.keys()-sky.keys()),gained=len(sky.keys()-base.keys()),
        relabeled=sum(base[k]!=sky[k] for k in base.keys()&sky.keys()),
        zero_strength_parity=True,elapsed_s=time.monotonic()-started)
    save(receipt,result)
    print('PREPARED',scan,metadata['base']['windows'],metadata['sky']['windows'],
          'relabeled',result['relabeled'],'seconds',round(result['elapsed_s'],1),flush=True)
    return result


def load(scan, variant):
    receipt = json.loads((HERE/'inputs'/scan/'receipt.json').read_text())
    assert receipt['dependencies']==signatures()
    kind = 'sky' if VARIANTS[variant][0] else 'base'
    path = HERE/'inputs'/scan/f'{kind}.npz'
    assert digest(path)==receipt['inputs'][kind]['input_sha256']
    with np.load(path) as z:
        data = SimpleNamespace(**{k:z[k].copy() for k in z.files})
    return data,receipt,kind


def make_objective(data, receipt, arm, variant):
    theta, frames, support, _ = bundle()
    return Objective(data,receipt['rf_center_hz'],arm,VARIANTS[variant][1],theta,frames,support)


def transfer(seed, data):
    numbers = seed['source_numbers']
    p = np.asarray(seed['parameters'])
    mapping = dict(zip(numbers,p[6:]))
    return dict(seed,parameters=np.r_[p[:6],[mapping.get(int(n),data.initial[6+i]) for i,n in enumerate(data.numbers)]])


def run_case(task):
    scan,arm,variant = task
    target = HERE/'initial'/f'{scan}-{arm}-{variant}.json'
    if target.exists():
        r = json.loads(target.read_text()); assert r['dependencies']==signatures()
        return str(target)
    begun = time.monotonic()
    d,receipt,kind = load(scan,variant)
    obj = make_objective(d,receipt,arm,variant)
    seeds = [transfer(s,d) for s in receipt['seed_records']]
    # Include both selection-derived timing starts in every arm and variant.
    for label in ('base','sky'):
        with np.load(HERE/'inputs'/scan/f'{label}.npz') as z:
            seeds.append(transfer(dict(parameters=z['initial'],source_numbers=z['numbers'],
                 coefficient=receipt['calibration_coefficient'],point_km=[0.,0.]),d))
    records = [reprice(obj,s,arm,f'common-seed-{i}') for i,s in enumerate(seeds)]
    roof_seed = next(s for s in seeds if np.linalg.norm(s['point_km'])<1e-8)
    roof = fit(obj,seed_vector(obj,roof_seed,arm),[0.,0.],BUDGET['roof_s'],True,radius_km=4.)
    roof['stage']='roof';records.append(roof)
    ordered = sorted(records,key=lambda r:r['objective'])
    first = ordered[0]
    second = next((r for r in ordered[1:] if np.linalg.norm(np.array(r['point_km'])-first['point_km'])>.1),ordered[1])
    for i,seed in enumerate((first,second,roof)):
        r = fit(obj,np.array(seed['vector']),seed['point_km'],BUDGET['search_s'],False,radius_km=4.)
        r['stage']=f'search-{i}';records.append(r)
    best = min(records,key=lambda r:r['objective'])
    info = diagnostics(obj,d,best)
    if not info['converged']:
        r = fit(obj,np.array(best['vector']),best['point_km'],BUDGET['polish_s'],False,radius_km=4.)
        r['stage']='polish';records.append(r)
    best = min(records,key=lambda r:r['objective']); info=diagnostics(obj,d,best)
    out = dict(scan=scan,arm=arm,variant=variant,dependencies=signatures(),input_kind=kind,
        input_sha256=receipt['inputs'][kind]['input_sha256'],windows=len(d.times),numbers=d.numbers,
        fit_original_rows=d.original_rows,evaluation_original_rows=d.original_rows,heldout_original_rows=[],
        radius_km=4.,strengths=VARIANTS[variant],maximum_budgets_s=BUDGET,
        records=records,best=best,roof=roof,elapsed_s=time.monotonic()-begun,**info)
    save(target,out)
    print('INITIAL',scan,arm,variant,round(info['distance_m']),'m','KKT',round(info['kkt'],5),flush=True)
    return str(target)


def cross_case(task):
    scan,arm,variant = task
    target = HERE/'final'/f'{scan}-{arm}-{variant}.json'
    if target.exists():
        r=json.loads(target.read_text());assert r['dependencies']==signatures();return str(target)
    d,receipt,kind=load(scan,variant);obj=make_objective(d,receipt,arm,variant)
    paths=[HERE/'initial'/f'{scan}-{a}-{v}.json' for a in ARMS for v in VARIANTS]
    pool=[json.loads(p.read_text()) for p in paths]
    out=next(r for r in pool if r['arm']==arm and r['variant']==variant)
    records=out['records']
    for r in pool:
        seed=transfer(dict(r['best'],source_numbers=r['numbers']),d)
        records.append(reprice(obj,seed,arm,'cross-seed'))
    best=min(records,key=lambda r:r['objective'])
    info=diagnostics(obj,d,best)
    if not info['converged']:
        r=fit(obj,np.array(best['vector']),best['point_km'],BUDGET['cross_s'],False,radius_km=4.)
        r['stage']='cross-polish';records.append(r)
    best=min(records,key=lambda r:r['objective']);info=diagnostics(obj,d,best)
    # Frequency-only score at the same point/input set, distinct from position error.
    reference=make_objective(d,receipt,arm,'control')
    common=diagnostics(reference,d,reprice(reference,best,arm,'no-cone-reference'))
    out.update(best=best,records=records,**info,cross_sources={str(p):digest(p) for p in paths},
               common_no_cone_data_nll=common['data_nll'])
    save(target,out)
    print('FINAL',scan,arm,variant,round(info['distance_m']),'m','KKT',round(info['kkt'],5),flush=True)
    return str(target)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--scans',nargs='+',default=SCANS)
    parser.add_argument('--workers',type=int,default=2)
    parser.add_argument('--stage',choices=['prepare','initial','final','all'],default='all')
    args=parser.parse_args()
    if not set(args.scans)<=set(SCANS):raise ValueError('N01--N16 only')
    protocol=dict(scope=__doc__,variants=VARIANTS,budgets=BUDGET,radius_km=4.,
       final_score=dict(sigma_hz=200.,detection_budget=.8,clutter_rate=2.,common_sigma_s=10.,relative_sigma_s=1/3,
                        total_timing_bound_s=20.,horizon='Q1 smooth 0--1 deg',weights='ordinary'),
       cone_prior='Frozen fitted-c 20-scan cone; marginal RX presence; neutral unsupported sky; total detection mass preserved.',
       data_policy='No new folds; all selected top-one windows fitted. Same per-selection observations and bank in both RF arms.',
       selection='Baseline count minus 10 per satellite, plus strength 1 mean RX log odds per satellite/5s; +/-3 cap.',
       position='Strength .5, multiplier floor .1; smooth evidence-support interpolation.',
       dependencies=signatures())
    save(HERE/'protocol.json',protocol)
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        if args.stage in ('prepare','all'):
            for f in as_completed([executor.submit(prepare_scan,s) for s in args.scans]):f.result()
        tasks=[(s,a,v) for s in args.scans for a in ARMS for v in VARIANTS]
        if args.stage in ('initial','all'):
            for f in as_completed([executor.submit(run_case,t) for t in tasks]):f.result()
        if args.stage in ('final','all'):
            for f in as_completed([executor.submit(cross_case,t) for t in tasks]):f.result()


if __name__=='__main__':main()
