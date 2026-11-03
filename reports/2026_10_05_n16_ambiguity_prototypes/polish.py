"""Equal bounded continuation allowance; original results remain unchanged."""
import argparse
import inspect
import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np

import experiment as ex

BUDGET = dict(slsqp_s=20., fisher_s=25.)


def run(task):
    scan, arm, mode = task
    source = ex.HERE/'results'/f'{scan}-{arm}-{mode}.json'
    target = ex.HERE/'polished'/source.name
    r = json.loads(source.read_text())
    receipt = dict(source_sha256=ex.digest(source), budgets=BUDGET,
        code_sha256=ex.digest(__file__), slsqp_sha256=ex.digest(inspect.getfile(ex.slsqp_fit)))
    if target.exists():
        assert json.loads(target.read_text())['continuation'] == receipt
        return str(target)
    begun = time.monotonic()
    data, meta, _, frozen, _ = ex.inputs(scan)
    obj = ex.Objective(data, meta['rf_center_hz'], arm, frozen, mode)
    records = r['records']
    if not ex.choose(records)['success']:
        records.append(ex.slsqp_fit(obj, ex.choose(records), BUDGET['slsqp_s'], radius_km=ex.RADIUS))
    if not ex.choose(records)['success']:
        records.append(ex.run_fit(obj, ex.choose(records), 'additional-fisher', BUDGET['fisher_s']))
    r['best'] = ex.choose(records)
    r['metrics'] = ex.metrics(obj, data, frozen, r['best'], arm, meta['rf_center_hz'])
    assert r['metrics']['hard_invisible_windows'] == 0
    r['continuation'] = receipt
    r['continuation_elapsed_s'] = time.monotonic()-begun
    ex.save(target, r)
    print('POLISHED',scan,arm,mode,round(r['metrics']['position_error_m']),
          'm KKT',round(r['metrics']['kkt'],6),'sec',round(time.monotonic()-begun,1),flush=True)
    return str(target)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--scans', nargs='+', choices=ex.SCANS, default=ex.SCANS)
    p.add_argument('--workers', type=int, default=3)
    a = p.parse_args()
    ex.save(ex.HERE/'polish-protocol.json', dict(scope=__doc__, budgets=BUDGET,
        code_sha256=ex.digest(__file__), stopping='stop when constrained KKT <= .001',
        nondifferentiability='Min-entropy has kinks at identity ties. The existing smooth KKT test may not certify a kink optimum; uncertified cases remain flagged.'))
    tasks = [(s,arm,m) for s in a.scans for m in ex.MODES for arm in ex.ARMS]
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        for f in as_completed([pool.submit(run,t) for t in tasks]): f.result()
