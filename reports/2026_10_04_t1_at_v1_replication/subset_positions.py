"""Bounded, independent 2 km position searches for frozen T1-AT associations.

Fitted-c membership/owners anchor both RF arms. Keep the fitted-c receiver
offset/line+spline baseline fixed, remove its RF term, then refit extra RX
lines, c and common/relative timing. No association reselection at trial sites.
Historical A/B results are references, not matched optimizer-budget controls.
"""
import argparse
import copy
import inspect
import json
import math
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from run import TopAbsoluteCalibration, BENCHMARK, HERE
from calibration import serial
from cohort import digest
from fisher_position import fit
from numeric_data import enable_research_model

ROOT = Path('/srv/bulk/leo/t1-at-v1-subset-positions-20261004')
ASSOCIATIONS = Path('/srv/bulk/leo/t1-at-v1-replication-20261004/attempt2')
INPUTS = Path('/srv/bulk/leo/ds13-18scan-benchmark-20261004/inputs-v2')


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, default=serial, indent=2, allow_nan=False))


def choose(owners, row_ids, margins, times, rms, ranking, fraction):
    if ranking == 'rms-cut':
        if not np.isfinite(fraction) or fraction <= 0:
            raise ValueError('RMS threshold must be positive and finite')
        selected = sorted(n for n in set(map(int, owners)) if rms[n] <= fraction)
        return selected, np.isin(owners, selected)
    if not 0 < fraction <= 1:
        raise ValueError('Fraction must be in (0, 1]')
    numbers = sorted(set(map(int, owners)))
    if ranking == 'glrt':
        order = np.lexsort((row_ids, -margins))
        keep = np.zeros(len(owners), bool)
        keep[order[:math.ceil(len(order)*fraction)]] = True
        return numbers, keep
    if ranking == 'rms':
        order = sorted(numbers, key=lambda n: (rms[n], n))
    elif ranking == 'support':
        order = sorted(numbers, key=lambda n: (-sum(owners == n), -float(np.ptp(times[owners == n])), n))
    else:
        raise ValueError('Unknown ranking')
    selected = sorted(order[:math.ceil(len(order)*fraction)])
    return selected, np.isin(owners, selected)


def prepare(scan):
    target = ROOT/scan/'input.npz'
    if target.exists():
        return
    directory = INPUTS/scan/'seed-timing-v6'
    cal = TopAbsoluteCalibration(directory)
    full = cal.data
    association = ASSOCIATIONS/scan/'fitted-c.json'
    receipt = json.loads(association.read_text())
    assigned = sorted(receipt['final']['assignments'], key=lambda a: a['row_index'])
    lookup = {int(r):i for i,r in enumerate(full.original_rows)}
    rows = np.array([lookup[a['row_index']] for a in assigned])
    owners = np.array([a['catalog_number'] for a in assigned])
    selected = {r['catalog_number']: r for r in receipt['final']['selected']}
    numbers = sorted(selected)
    columns = np.array([int(np.flatnonzero(full.numbers == n)[0]) for n in numbers])
    # Recover the frozen fitted-c receiver baseline in prediction-feature order.
    fixed = np.zeros(cal.group_count)
    rf_correction = np.zeros(cal.group_count)
    coefficients = []
    for fold, (destination, part, models) in enumerate(cal.parts):
        record = json.loads((directory/'calibration-v2'/f'fold-{fold}.json').read_text())
        coefficient = record['arms']['fitted-c']['coefficient']
        parameters, _, correction = models['fitted-c']
        rf = coefficient*(part.rf-record['rf_center_hz'])/1e9
        fixed[destination] = (correction-rf+parameters[2+2*part.receiver]
                              +parameters[3+2*part.receiver]*(part.times-150.))
        rf_correction[destination] = rf
        coefficients.append(coefficient)
    fixed = fixed[cal.inverse][rows]
    rf_correction = rf_correction[cal.inverse][rows]
    data = copy.copy(full)
    for key in ('times','measured','rf','receiver','channel','group','margin','original_rows'):
        setattr(data, key, getattr(full, key)[rows].copy())
    data.measured -= fixed
    data.numbers = np.asarray(numbers)
    data.position, data.velocity = full.position[columns], full.velocity[columns]
    data.initial = np.r_[full.initial[:2], np.zeros(4), [selected[n]['offset_s'] for n in numbers]]
    from prediction_plan import SharedPredictionPlan
    prediction, _, _ = SharedPredictionPlan(data, np.arange(len(numbers))).predict(data.initial)
    expected = np.column_stack([cal.predict('fitted-c', np.array([sid]), data.initial[6+j])[0][rows,0]
                                for j,sid in enumerate(columns)])
    reconstruction = np.max(abs(prediction.reshape(expected.shape)+fixed[:,None]+rf_correction[:,None]-expected))
    assert reconstruction < 1e-5, reconstruction
    target.parent.mkdir(parents=True, exist_ok=True)
    fields = ('times','measured','rf','receiver','channel','group','margin','original_rows',
              'numbers','position','velocity','nodes','initial')
    np.savez_compressed(target, **{k:getattr(data,k) for k in fields}, owners=owners,
                        fixed_receiver_hz=fixed)
    save(target.with_suffix('.json'), dict(scan=scan, scope=__doc__, sources=cal.sources,
         association_source=str(ASSOCIATIONS/scan/'fitted-c.json'),
         association_sha256=digest((ASSOCIATIONS/scan/'fitted-c.json').read_bytes()),
         input_sha256=digest(target.read_bytes()), reconstruction_max_hz=float(reconstruction),
         seed_coefficient=float(np.median(coefficients)), rf_center_hz=float(np.mean(np.unique(full.rf))),
         bank_policy='Fitted-c selected satellites; identical bank/subset in RF arms. GLRT subsets retain full anchored bank.'))


def design():
    rng = np.random.default_rng(20261004)
    points = []
    for radius in (.7, 1.4, 2.):
        for sector in range(4):
            angle = rng.uniform(sector*np.pi/2, (sector+1)*np.pi/2)
            points.append(radius*np.array([np.sin(angle), np.cos(angle)]))
    points += [2*np.array([np.sin(j*np.pi/4), np.cos(j*np.pi/4)]) for j in range(8)]
    return points


def run_case(task):
    scan, ranking, fraction = task
    case = f'rms-cut-{fraction:g}' if ranking == 'rms-cut' else 'all-100' if fraction == 1 else f'{ranking}-{int(100*fraction)}'
    output = ROOT/scan/f'{case}.json'
    if output.exists():
        return str(output)
    enable_research_model()
    from rf_calibration_diagnostic import CalibrationObjective
    from timing_model import TimingObjective
    meta = json.loads((ROOT/scan/'input.json').read_text())
    with np.load(ROOT/scan/'input.npz') as z:
        full = SimpleNamespace(**{k:z[k].copy() for k in z.files})
    if fraction == 1:
        keep, numbers = np.ones(len(full.times), bool), full.numbers.tolist()
        full_result = None
    else:
        full_result = json.loads((ROOT/scan/'all-100.json').read_text())
        rms = {int(n):v for n,v in full_result['roof_owner_rms_hz'].items()}
        numbers, keep = choose(full.owners, full.original_rows, full.margin, full.times, rms, ranking, fraction)
    if not numbers or not np.any(keep):
        save(output, dict(scan=scan, ranking=ranking, fraction=fraction, case_id=case,
                          windows=0, candidates=0, arms={}, state='empty-subset',
                          reason='No satellite passes the frozen roof RMS threshold'))
        return str(output)
    columns = np.array([int(np.flatnonzero(full.numbers == n)[0]) for n in numbers])
    data = copy.copy(full)
    for key in ('times','measured','rf','receiver','channel','group','margin','original_rows','owners'):
        setattr(data, key, getattr(full,key)[keep].copy())
    data.numbers = full.numbers[columns]
    data.position, data.velocity = full.position[columns], full.velocity[columns]
    result = dict(scan=scan, ranking=ranking, fraction=fraction, case_id=case, windows=len(data.times),
                  candidates=len(numbers), numbers=numbers, original_rows=data.original_rows,
                  scope=__doc__, input_metadata=meta,
                  implementation={str(p):digest(p.read_bytes()) for p in (Path(__file__), Path(inspect.getfile(fit)),
                                      Path(inspect.getfile(CalibrationObjective)),Path(inspect.getfile(TimingObjective)))},
                  budgets=dict(roof_s=12, probe_s=1.5, three_searches_s=12, transfer_fixed_s=6, transfer_joint_s=12,
                               neighbor_s=2, final_joint_s=12), arms={})
    for arm in ('fitted-c','zero-c'):
        if full_result:
            seed = full_result['arms'][arm]['roof']
            physical = np.asarray(seed['parameters'])
            data.initial = np.r_[physical[:6], physical[6+columns]]
            coefficient = seed['coefficient']
        else:
            data.initial = np.r_[full.initial[:6], full.initial[6+columns]]
            coefficient = meta['seed_coefficient']
        objective = CalibrationObjective(data, data.initial, np.arange(len(numbers)), False, 12.)
        objective.center = meta['rf_center_hz']
        objective.features = ((data.rf-objective.center)/1e9)[:,None]
        objective.likelihood.features = objective.features
        objective.base.minimum_shift_s = max(objective.base.minimum_shift_s, -20.)
        objective.base.maximum_shift_s = min(objective.base.maximum_shift_s, 20.)
        if arm == 'zero-c': objective.bounds[-1] = (0.,0.)
        initial = objective.initial.copy()
        initial[-1] = coefficient if arm == 'fitted-c' else 0.
        records = []
        def fitted(name, start, point, budget, fixed):
            r = fit(objective, start, point, budget, fixed)
            r['stage'] = name
            records.append(r)
            return r
        roof = fitted('roof', initial, [0.,0.], 12., True)
        for i,point in enumerate(design()):
            fitted(f'probe-{i}', roof['vector'], point, 1.5, True)
        starts = [roof]
        for r in sorted(records, key=lambda r:r['objective']):
            if all(np.linalg.norm(np.asarray(r['point_km'])-s['point_km'])>.4 for s in starts): starts.append(r)
            if len(starts)==3: break
        for i,s in enumerate(starts): fitted(f'search-{i}', s['vector'], s['point_km'], 12., False)
        best = min(records, key=lambda r:r['objective'])
        transfer = fitted('roof-transfer', best['vector'], [0.,0.], 6., True)
        roof = min([roof,transfer], key=lambda r:r['objective'])
        transfer = fitted('best-transfer', roof['vector'], best['point_km'], 6., True)
        fitted('joint-transfer', transfer['vector'], transfer['point_km'], 12., False)
        best = min(records, key=lambda r:r['objective'])
        for i,axis in enumerate(np.eye(2)):
            for sign in (-1,1):
                point = np.asarray(best['point_km']) + sign*.025*axis
                if np.linalg.norm(point)>2: point *= 2/np.linalg.norm(point)
                fitted(f'neighbor-{i}-{sign}', best['vector'], point, 2., True)
        best = min(records, key=lambda r:r['objective'])
        fitted('final-joint', best['vector'], best['point_km'], 12., False)
        best = min(records, key=lambda r:r['objective'])
        # Prefer a stationary solution when scores differ only by roundoff.
        equivalent = [r for r in records if r['success'] and not r['fixed_location'] and r['objective']<=best['objective']+1e-7]
        if equivalent: best = min(equivalent, key=lambda r:r['objective'])
        joint = [r for r in records if not r['fixed_location'] and r['success']]
        ambiguous = any(np.linalg.norm(np.asarray(r['point_km'])-best['point_km'])>.1 and abs(r['objective']-best['objective'])<1 for r in joint)
        result['arms'][arm] = dict(roof=roof, best=best, records=records,
            distance_m=float(1000*np.linalg.norm(best['point_km'])),
            boundary=bool(np.linalg.norm(best['point_km'])>1.999),
            converged=bool(best['success'] and not best['fixed_location']),
            ambiguous=ambiguous, delta_score=best['objective']-roof['objective'])
        if fraction == 1 and arm == 'fitted-c':
            from prediction_plan import SharedPredictionPlan
            from refinement import circular
            prediction, _, _ = SharedPredictionPlan(data,np.arange(len(numbers))).predict(np.array(roof['parameters']))
            prediction = prediction.reshape(len(data.times),-1) + roof['coefficient']*(data.rf[:,None]-objective.center)/1e9
            errors = circular(data.measured-np.array([prediction[i,numbers.index(int(n))] for i,n in enumerate(data.owners)]))
            result['roof_owner_rms_hz'] = {int(n):float(np.sqrt(np.mean(errors[data.owners==n]**2))) for n in numbers}
        save(ROOT/scan/f'{case}-partial.json', result)
        print(scan, case, arm, round(result['arms'][arm]['distance_m']), best['success'], best['status'], flush=True)
    save(output, result)
    return str(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    for scan in ('N01','N02'): prepare(scan)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for future in as_completed([pool.submit(run_case,(s,'support',1.)) for s in ('N01','N02')]): print('DONE',future.result(),flush=True)
        jobs = [pool.submit(run_case,(s,r,f)) for s in ('N01','N02') for r in ('rms','support','glrt') for f in (.25,.5,.75)]
        for future in as_completed(jobs): print('DONE',future.result(),flush=True)
