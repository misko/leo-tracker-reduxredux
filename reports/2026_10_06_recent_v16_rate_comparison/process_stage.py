"""One checkpointed recent-scan V16 stage; immutable recordings read-only.

Fresh scan starts replace the historical score-sweep seed pool. No old scan's
nuisance values or position result is transferred; no calibration folds.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BENCH = ROOT/'reports/2026_10_04_ds13_18_scan_benchmark'
BASE = ROOT/'reports/2026_10_04_t1_at_v1_replication'
WORK = Path('/srv/bulk/leo/recent-v16-rates-20261006')
COHORT = HERE/'cohort-final.json'
STAGES = ('export', 'bank', 'refine', 'bootstrap', 'calibrate', 'associate', 'position')
sys.path[:0] = [str(BASE), str(BENCH)]
ARMS = ('fitted-c', 'zero-c')
POSITION_BUDGET = dict(roof_s=5., probe_s=1., search_s=8., search_starts=3,
                       polish_s=15., slsqp_s=20., continuation_fisher_s=10.)


def sha(path):
    return 'sha256:'+hashlib.sha256(Path(path).read_bytes()).hexdigest()


def configure():
    from numeric_data import enable_research_model
    enable_research_model()
    import full_data_calibration as calibration
    calibration.INPUTS = WORK/'inputs'
    calibration.OUT = WORK/'fits'
    return calibration


def save(path, value):
    from calibration import serial
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(value, stream, default=serial, indent=2, allow_nan=False)


def prepare(label):
    import numpy as np
    calibration = configure()
    cal = calibration.FullCalibration(label)
    raw = cal.data
    association_path = WORK/'fits'/label/'associations/fitted-c.json'
    association = json.loads(association_path.read_text())
    assigned = sorted(association['final']['assignments'], key=lambda r: r['row_index'])
    if len(assigned) < 20:
        raise ValueError('Insufficient assigned windows for a position fit')
    if len({r['row_index'] for r in assigned}) != len(assigned):
        raise ValueError('Duplicate assigned observation')
    lookup = {int(row): i for i, row in enumerate(raw.original_rows)}
    rows = np.array([lookup[r['row_index']] for r in assigned], int)
    selected = {int(r['catalog_number']): r for r in association['final']['selected']}
    if not {int(r['catalog_number']) for r in assigned} <= set(selected):
        raise ValueError('Assigned owner missing from selected satellite bank')
    numbers = sorted(selected)
    columns = np.array([int(np.flatnonzero(raw.numbers==n)[0]) for n in numbers])
    data = copy.copy(raw)
    for key in ('times','measured','rf','receiver','channel','group','margin','original_rows'):
        setattr(data, key, getattr(raw, key)[rows].copy())
    if len(np.unique(data.group)) != len(data.times):
        raise ValueError('Position fitting requires exactly one candidate per window')
    data.numbers = raw.numbers[columns]
    data.position = raw.position[columns]
    data.velocity = raw.velocity[columns]
    data.fixed_receiver_hz = cal.receiver_baseline('fitted-c')[rows]
    data.measured -= data.fixed_receiver_hz
    data.owners = np.array([r['catalog_number'] for r in assigned])
    data.initial = np.r_[raw.initial[:2], np.zeros(4), [selected[n]['offset_s'] for n in numbers]]
    metadata = dict(rf_center_hz=cal.record['rf_center_hz'], raw_sources=raw.sources,
        calibration_source=str(cal.path), calibration_sha256=sha(cal.path),
        association_source=str(association_path), association_sha256=sha(association_path),
        selection='All fitted-c-associated top-one windows; frozen identical observations, bank and receiver baseline for both final RF arms',
        calibration_coefficient={arm:cal.record['arms'][arm]['coefficient'] for arm in ARMS})
    return data, metadata


def position(label, *, model='V16', spec_key='V16', objective_factory=None,
             destination=None, experiment=None):
    import numpy as np
    from position_score_sweep import Objective, SPECS, finish
    from timing_bound_comparison import feasible_start
    from convergence_fisher import fit
    from resume_position_convergence import best_record
    from polish_position_score_sweep import slsqp_fit
    data, metadata = prepare(label)
    folder = destination or WORK/'positions'/label
    folder.mkdir(parents=True, exist_ok=True)
    source = folder/'input.npz'
    fields = ('times','measured','rf','receiver','channel','group','margin','original_rows','owners',
              'numbers','position','velocity','nodes','initial','fixed_receiver_hz')
    if not source.exists():
        np.savez_compressed(source, **{k:getattr(data,k) for k in fields})
    else:
        with np.load(source, allow_pickle=False) as saved:
            for key in fields:
                np.testing.assert_array_equal(saved[key], getattr(data,key))
    if not (folder/'input.json').exists():
        save(folder/'input.json', dict(input_metadata=metadata, input_sha256=sha(source)))
    # All starts and budgets declared before seeing position error. The same
    # association timing and zero-timing families are offered in both RF arms.
    for arm in ARMS:
        path = folder/f'{arm}.json'
        if path.exists():
            old = json.loads(path.read_text())
            assert old['input_sha256']==sha(source) and old['spec']==SPECS[spec_key]
            assert old['maximum_budgets_s']==POSITION_BUDGET and old['radius_km']==4.
            assert old.get('experiment')==experiment and old['model']==model
            continue
        begun = time.monotonic()
        factory = objective_factory or Objective
        obj = factory(data, metadata['rf_center_hz'], arm, SPECS[spec_key])
        records = []
        def fitted(stage, seed, point, budget, fixed=False):
            r = fit(obj, feasible_start(obj, seed, 20., arm), point, budget, fixed, radius_km=4.)
            r['stage'] = stage
            records.append(r)
            return r
        coefficient = metadata['calibration_coefficient'][arm]
        initial = dict(parameters=data.initial.copy(), coefficient=coefficient, point_km=[0.,0.])
        zero = copy.deepcopy(initial)
        zero['parameters'][6:] = 0.
        roofs = [fitted('roof-'+name, seed, [0.,0.], POSITION_BUDGET['roof_s'], True)
                 for name, seed in [('association',initial), ('zero-timing',zero)]]
        roof = min(roofs, key=lambda r:r['objective'])
        probes = [fitted(f'probe-{i}',roof,3.2*np.array([np.cos(angle),np.sin(angle)]),
                         POSITION_BUDGET['probe_s'], True)
                  for i, angle in enumerate(np.arange(4)*np.pi/2)]
        for i, seed in enumerate([roof, *sorted(probes, key=lambda r:r['objective'])[:2]]):
            fitted(f'search-{i}', seed, seed['point_km'], POSITION_BUDGET['search_s'])
        best = best_record(records)
        fitted('polish', best, best['point_km'], POSITION_BUDGET['polish_s'])
        best = best_record(records)
        if not finish(obj,data,best)['converged']:
            records.append(slsqp_fit(obj,best,POSITION_BUDGET['slsqp_s'],radius_km=4.))
            best = best_record(records)
        if not finish(obj,data,best)['converged']:
            fitted('continuation-fisher',best,best['point_km'],POSITION_BUDGET['continuation_fisher_s'])
            best = best_record(records)
        metrics = finish(obj,data,best)
        roof_metrics = finish(obj,data,roof)
        result = dict(scan=label, arm=arm, model=model, spec=SPECS[spec_key],
            experiment=experiment,
            search_protocol='Fresh association/zero-timing roof starts, four cardinal probes, three local starts, matched continuation; no historical cross-model seed pool',
            implementation_sha256=sha(__file__), input_sha256=sha(source), input_metadata=metadata,
            position_score_source_sha256=sha(BASE/'position_score_sweep.py'),
            maximum_budgets_s=POSITION_BUDGET, radius_km=4.,
            fit_original_rows=data.original_rows, evaluation_original_rows=data.original_rows,
            heldout_original_rows=[], windows=len(data.times), numbers=data.numbers,
            best=best, roof=roof, records=records, elapsed_s=time.monotonic()-begun, **metrics)
        result.update(roof_metrics=roof_metrics,
            score_change_from_roof=metrics['objective']-roof_metrics['objective'],
            roof_position_gradient_per_km=roof['position_gradient_per_km'])
        save(path,result)
        print('POSITION_RESULT',json.dumps({k:result[k] for k in
            ('scan','arm','distance_m','converged','boundary','posterior_weighted_residual_rms_hz')}),flush=True)


def run(stage,label):
    scans=json.loads(COHORT.read_text())['scans']
    scan=next(r for r in scans if r['label']==label)
    folder=WORK/'inputs'/label
    folder.mkdir(parents=True,exist_ok=True)
    if stage=='export':
        from export_observations import export
        export(scan,folder/'observations.json',sha(COHORT))
    elif stage=='bank':
        from orbit_bank import build
        build(folder/'observations.json')
    elif stage=='refine':
        if (folder/'refinement/refined.json').exists():
            from numeric_data import load
            load(folder)
            return
        sys.path.insert(0,str(ROOT/'reports/2026_10_05_receiver_sky_82'))
        import cached_refinement as cached
        import run_refinement as baseline
        refinement_workers = int(os.environ.get('RECENT_V16_REFINEMENT_WORKERS','2'))
        if refinement_workers not in (1,2,4):
            raise ValueError('Refinement supports a bounded 1, 2 or 4 numerical workers')
        # Execution-only override: identical independent visit tasks and
        # checkpoint signatures. Allows moving the finished 2.5 MS/s workers
        # to the one remaining 10 MS/s scan without increasing total RF workers.
        if refinement_workers == 4:
            from concurrent.futures import ProcessPoolExecutor
            def four_workers(**kwargs):
                kwargs['max_workers'] = 4
                return ProcessPoolExecutor(**kwargs)
            baseline.ProcessPoolExecutor = four_workers
        destination=folder/'refinement'
        destination.mkdir(exist_ok=True)
        if not (destination/'cache-parity.json').exists():
            save(destination/'cache-parity.json',cached.parity(folder/'observations.json'))
        baseline.worker=cached.cached_worker
        sys.argv=['run_refinement',str(folder/'observations.json'),'--workers',str(min(2,refinement_workers))]
        print('REFINEMENT_EXECUTION_WORKERS',refinement_workers,flush=True)
        baseline.main()
    elif stage=='bootstrap':
        from bootstrap_tracks import run as bootstrap
        from seed_timing_variant import run as seed
        if not (folder/'bootstrap.json').exists():bootstrap(folder)
        if not (folder/'seed-timing-v6/bootstrap.json').exists():seed(folder)
    elif stage=='calibrate':
        calibration=configure()
        record=calibration.calibrate(label)
        if not record['converged']:raise ValueError('Calibration is unconverged; position stage is blocked')
    elif stage=='associate':
        configure().associate(label)
    elif stage=='position':
        configure()
        position(label)
    else:
        raise ValueError(stage)
    print('STAGE_COMPLETE',label,stage,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage',choices=STAGES)
    p.add_argument('label')
    a=p.parse_args()
    run(a.stage,a.label)
