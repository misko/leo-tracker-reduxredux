"""Matched convergence-only continuation; no new data, starts, or model choices.

Offer every case 25 s SLSQP then 20 s Fisher, stopping at the unchanged KKT <=
0.001 test. Preserve the earlier final-stage file and choose by objective only.
"""
import argparse
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import position_structure_study as study

BUDGETS = dict(slsqp_s=25., fisher_s=20.)


def run(task):
    scan, arm, mode = task
    source = study.OUT/'final'/f'{scan}-{arm}-{mode}.json'
    target = study.OUT/'polished'/source.name
    implementation = study.previous.digest(Path(__file__))
    if target.exists():
        r = json.loads(target.read_text())
        assert r['continuation']['source_sha256'] == study.previous.digest(source)
        assert r['continuation']['implementation_sha256'] == implementation
        return str(target)
    data, saved, _, _, _ = study.inputs(scan)
    obj = study.make_objective(data, saved, arm, mode)
    r = json.loads(source.read_text())
    records = r['records']
    for algorithm in ['slsqp', 'fisher']:
        best = study.previous.best_record(records)
        if study.metrics(obj, data, best)['converged']: break
        if algorithm == 'slsqp':
            new = study.slsqp_fit(obj, best, BUDGETS['slsqp_s'])
            new['coefficient'] = float(new['vector'][obj.size])
            new['stage'] = 'matched-slsqp-continuation'
        else:
            new = study.fitted(obj, best, 'matched-fisher-continuation', BUDGETS['fisher_s'])
        records.append(new)
    best = study.previous.best_record(records)
    assert best['objective'] <= r['objective']+1e-7
    reference = study.previous.objective(data, saved, arm, 'C1')
    common = study.previous.finish(reference, data, study.reprice(reference, best, arm, 'common-reference'))
    r.update(best=best, **study.metrics(obj, data, best),
        common_reference_data_nll=common['data_nll'],
        continuation=dict(scope=__doc__, source_sha256=study.previous.digest(source),
            implementation_sha256=implementation, maximum_budgets_s=BUDGETS,
            original_converged=r['converged'], original_distance_m=r['distance_m']))
    study.previous.save(target, r)
    print('POLISHED', scan, arm, mode, round(r['distance_m']), 'm', 'KKT', round(r['kkt'],5), flush=True)
    return str(target)


def report():
    rows = study.collect('polished')
    implementation = study.previous.digest(Path(__file__))
    for r in rows:
        source = study.OUT/'final'/f'{r["scan"]}-{r["arm"]}-{r["mode"]}.json'
        assert r['continuation']['source_sha256'] == study.previous.digest(source)
        assert r['continuation']['implementation_sha256'] == implementation
        assert r['continuation']['maximum_budgets_s'] == BUDGETS
        paths = [study.OUT/'initial'/f'{r["scan"]}-{a}-{m}.json' for a in study.ARMS for m in study.MODES]
        assert r['cross_sources'] == {str(p):study.previous.digest(p) for p in paths}
    study.report('polished')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scans', nargs='+', choices=study.SCANS, default=study.SCANS)
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--report-only', action='store_true')
    args = parser.parse_args()
    if args.report_only: report()
    else:
        jobs = [(s,a,m) for s in args.scans for m in study.MODES for a in study.ARMS]
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            for future in as_completed([pool.submit(run,j) for j in jobs]): future.result()
