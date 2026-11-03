"""One matched cross-prior/RF restart round, selected only by model score.

Every case sees the same frozen eight candidate solutions (4 priors x 2 RF
arms) from the completed continuation stage for its scan. Reprice with the
case's own prior and RF constraint, then continue the lowest-score candidate
for up to 3 x 20 seconds, stopping at KKT <= 1e-3. This tests discovered local
branches, not a global minimum certificate. No truth-selected starting points.
"""
import argparse
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

import full_data_timing_priors as experiment
from audit_post_scan_tle import diagnostics
from convergence_fisher import fit
from resume_position_convergence import best_record
from subset_positions import serial
from timing_bound_comparison import digest

SOURCE = experiment.OUT/'polished'
OUT = experiment.OUT/'cross-start'
BUDGETS = (20., 20., 20.)


def run(task):
    scan, arm, mode = task
    paths = {(a, m): SOURCE/f'{scan}-{a}-{m}.json' for a in experiment.ARMS for m in experiment.PRECISIONS}
    hashes = {str(p): digest(p) for p in paths.values()}
    target = OUT/paths[arm, mode].name
    if target.exists():
        r = json.loads(target.read_text())
        assert r['cross_start']['sources'] == hashes
        assert r['cross_start']['implementation_sha256'] == digest(Path(__file__))
        return str(target)
    inputs = {k: json.loads(p.read_text()) for k, p in paths.items()}
    r = inputs[arm, mode]
    data, saved, _ = experiment.load(scan)
    obj = experiment.objective(data, saved, arm, mode)
    seeds = [experiment.reprice(obj, v['best'], arm, f'cross-seed-{a}-{m}') for (a, m), v in inputs.items()]
    available_gain = r['objective']-min(z['objective'] for z in seeds)
    r['records'].extend(seeds)
    for attempt, budget in enumerate(BUDGETS):
        start = best_record(r['records'])
        if diagnostics(obj, data, start)['converged']: break
        fitted = fit(obj, np.asarray(start['vector']), start['point_km'], budget, False, radius_km=4.)
        fitted['stage'] = f'cross-prior-continuation-{attempt}'
        r['records'].append(fitted)
    best = best_record(r['records'])
    metrics = diagnostics(obj, data, best)
    assert metrics['objective'] <= min(z['objective'] for z in seeds)+1e-7
    r.update(best=best, **metrics)
    r['timing'] = experiment.timing_and_gradient(obj, best)
    r['cross_start'] = dict(scope=__doc__, sources=hashes, maximum_pass_budgets_s=BUDGETS,
                            implementation_sha256=digest(Path(__file__)), available_seed_gain_nll=available_gain)
    target.write_text(json.dumps(r, default=serial, indent=2, allow_nan=False))
    print('CROSS-START', scan, arm, mode, round(r['distance_m']), 'm',
          'converged', r['converged'], 'KKT', round(r['kkt'], 6),
          'seed gain', round(available_gain, 4), flush=True)
    return str(target)


def main():
    p = argparse.ArgumentParser(); p.add_argument('--workers', type=int, default=8)
    p.add_argument('--render-only', action='store_true'); args = p.parse_args()
    OUT.mkdir(exist_ok=True)
    if not args.render_only:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            jobs = [pool.submit(run, (s, a, m)) for s in experiment.SCANS for a in experiment.ARMS for m in experiment.PRECISIONS]
            for f in as_completed(jobs): f.result()
    experiment.OUT = OUT
    rows = experiment.collect(experiment.SCANS)
    for r in rows:
        assert all(digest(Path(p)) == sha for p, sha in r['cross_start']['sources'].items())
        assert r['cross_start']['maximum_pass_budgets_s'] == list(BUDGETS)
        assert r['cross_start']['implementation_sha256'] == digest(Path(__file__))
    summary = experiment.summarize(rows)
    experiment.render(rows, summary, experiment.SCANS)
    audit = dict(passed=True, cases=len(rows), scope=__doc__, summaries=summary,
                 dependencies=experiment.dependencies(), implementation_sha256=digest(Path(__file__)),
                 all_inputs_and_objectives_reconstructed=True, matched_rf_arms_and_priors=True,
                 cross_seed_count=8, maximum_pass_budgets_s=BUDGETS,
                 notes=['No satellite reselection or calibration changes.',
                        'Roof-gradient diagnostics are inherited from the separately profiled continuation stage.',
                        'Final solutions chosen by penalized model score; compare data fit and position error separately.'])
    (OUT/'audit.json').write_text(json.dumps(audit, default=serial, indent=2, allow_nan=False))
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    main()
