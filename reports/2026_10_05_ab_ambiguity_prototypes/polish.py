"""Matched convergence continuation; preserve initial fits and model semantics.

All cases get the same maximum policy, stopping when the current best meets
KKT<=1e-3: SLSQP 20 seconds then Fisher 25 seconds. Roof nuisance profiles get
up to 12 seconds when needed, and a joint cross-start if that improves the best
score. No tolerance relaxation, parameter changes or position-error selection.
"""
import json
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np

from experiment import (HERE, MODES, ARMS, inputs, Objective, run_fit, choose,
                        metrics, digest, save)
from position_direct import fit as slsqp


def run(task):
    scan, arm, mode = task
    source = HERE/'results'/f'{scan}-{arm}-{mode}.json'
    target = HERE/'polished'/source.name
    if target.exists():
        old = json.loads(target.read_text())
        if old['continuation']['source_sha256'] != digest(source):
            raise ValueError('Continuation source changed')
        return str(target)
    record = json.loads(source.read_text())
    data, meta, _, frozen, _ = inputs(scan)
    obj = Objective(data, meta['rf_center_hz'], frozen, arm, mode)
    extra = []
    records = [record['best']]
    for stage in ('slsqp', 'fisher'):
        best = choose(records)
        if best['success']:
            break
        if stage == 'slsqp':
            r = slsqp(obj, np.asarray(best['vector']), best['point_km'], 20., False)
            r['stage'] = 'continuation-slsqp'
        else:
            r = run_fit(obj, best, 'continuation-fisher', 25.)
        records.append(r); extra.append(r)
    best = choose(records)
    roof = record['roof']
    if not roof['success']:
        newroof = run_fit(obj, roof, 'continuation-roof', 12., True)
        extra.append(newroof)
        roof = choose([roof, newroof])
    if roof['objective'] < best['objective']-1e-7:
        r = run_fit(obj, roof, 'continuation-roof-cross', 15.)
        records.append(r); extra.append(r)
        best = choose(records)
    result = dict(record)
    result.update(best=best, roof=roof,
        metrics=metrics(obj, data, frozen, best, arm, meta['rf_center_hz']),
        roof_metrics=dict(converged=roof['success'], kkt=roof['kkt_residual'],
            gradient_per_100m=(np.asarray(roof['position_gradient_per_km'])*.1).tolist(),
            gradient_norm_per_100m=float(np.linalg.norm(roof['position_gradient_per_km'])*.1)),
        elapsed_s=record['elapsed_s']+sum(r['elapsed_s'] for r in extra),
        continuation=dict(scope=__doc__, source_sha256=digest(source),
                          implementation_sha256=digest(HERE/'polish.py'), records=extra))
    save(target, result)
    print('POLISHED', scan, arm, mode, round(result['metrics']['position_error_m']), 'm',
          'KKT', round(best['kkt_residual'], 6), 'roof', roof['success'], flush=True)
    return str(target)


if __name__ == '__main__':
    jobs = [(s, a, m) for s in ('A', 'B') for m in MODES for a in ARMS]
    with ProcessPoolExecutor(max_workers=3) as pool:
        for future in as_completed([pool.submit(run, job) for job in jobs]):
            future.result()
