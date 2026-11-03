"""Matched extra convergence allowance; never choose fits by roof error."""
import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

import experiment as study

BUDGET_S = 20.


def choose(records):
    lowest = min(r['objective'] for r in records)
    tolerance = 64*np.finfo(float).eps*max(1., abs(lowest))
    tied = [r for r in records if r['objective'] <= lowest+tolerance]
    return min(tied, key=lambda r:r['kkt_residual'])


def run(task):
    scan, arm, variant = task
    source = study.HERE/'final'/f'{scan}-{arm}-{variant}.json'
    target = study.HERE/'polished'/source.name
    sha = study.digest(source)
    implementation = study.digest(Path(__file__))
    if target.exists():
        r = json.loads(target.read_text())
        assert r['polish_source_sha256'] == sha and r['polish_implementation_sha256'] == implementation
        return str(target)
    started = time.monotonic()
    out = json.loads(source.read_text())
    assert out['dependencies'] == study.signatures()
    data, receipt, _ = study.load(scan, variant)
    obj = study.make_objective(data, receipt, arm, variant)
    best = choose(out['records'])
    info = study.diagnostics(obj, data, best)
    if not info['converged']:
        r = study.fit(obj, np.array(best['vector']), best['point_km'], BUDGET_S, False, radius_km=4.)
        r['stage'] = 'matched-convergence-polish'
        out['records'].append(r)
        best = choose(out['records'])
        info = study.diagnostics(obj, data, best)
    reference = study.make_objective(data, receipt, arm, 'control')
    common = study.diagnostics(reference, data, study.reprice(reference, best, arm, 'no-cone-reference'))
    out.update(best=best, **info, common_no_cone_data_nll=common['data_nll'],
               polish_source=str(source), polish_source_sha256=sha,
               polish_implementation_sha256=implementation, additional_polish_allowance_s=BUDGET_S,
               polish_elapsed_s=time.monotonic()-started)
    study.save(target, out)
    print('POLISHED', scan, arm, variant, round(info['distance_m']), 'm',
          'KKT', round(info['kkt'],5), flush=True)
    return str(target)


def main():
    tasks = [(s,a,v) for s in study.SCANS for a in study.ARMS for v in study.VARIANTS]
    assert all((study.HERE/'final'/f'{s}-{a}-{v}.json').exists() for s,a,v in tasks)
    with ProcessPoolExecutor(max_workers=2) as pool:
        for f in as_completed([pool.submit(run, task) for task in tasks]):
            f.result()


if __name__ == '__main__':
    main()
