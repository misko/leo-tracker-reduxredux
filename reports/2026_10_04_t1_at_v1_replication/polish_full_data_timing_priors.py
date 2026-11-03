"""Matched bounded convergence continuation; no new starts or model changes.

Every prior/RF pair receives the same stop rule and maximum continuation budget:
up to three 20-second Fisher passes, stopping at the unchanged KKT tolerance.
Archived first-pass results remain untouched. Roof nuisance-only fits receive
the same continuation separately for trustworthy profile-gradient diagnostics.
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
from timing_bound_comparison import digest
from subset_positions import serial

SOURCE = experiment.OUT
OUT = SOURCE/'polished'
BUDGETS = (20., 20., 20.)


def run(task):
    scan, arm, mode = task
    source = SOURCE/f'{scan}-{arm}-{mode}.json'
    target = OUT/source.name
    if target.exists():
        r = json.loads(target.read_text())
        assert r['continuation']['source_sha256'] == digest(source)
        assert r['continuation']['implementation_sha256'] == digest(Path(__file__))
        return str(target)
    r = json.loads(source.read_text())
    data, saved, _ = experiment.load(scan)
    obj = experiment.objective(data, saved, arm, mode)
    roofs = [r['roof']]
    for attempt, budget in enumerate(BUDGETS):
        start = min(roofs, key=lambda z: z['objective'])
        if start['success']: break
        fitted = fit(obj, np.asarray(start['vector']), [0., 0.], budget, True, radius_km=4.)
        fitted['stage'] = f'roof-continuation-{attempt}'
        roofs.append(fitted)
    r['roof'] = min(roofs, key=lambda z: z['objective'])
    r['roof_diagnostics'] = experiment.timing_and_gradient(obj, r['roof'])
    r['roof_diagnostics']['nuisance_converged'] = bool(r['roof']['success'])
    # A better roof fit is also a feasible candidate; never hide a lower-score
    # solution merely because it came from a diagnostic nuisance fit.
    r['records'].extend(roofs[1:])
    for attempt, budget in enumerate(BUDGETS):
        start = best_record(r['records'])
        # Reconstruct stationarity instead of trusting cached success flags.
        check = diagnostics(obj, data, start)
        if check['converged']: break
        fitted = fit(obj, np.asarray(start['vector']), start['point_km'], budget, False, radius_km=4.)
        fitted['stage'] = f'continuation-{attempt}'
        r['records'].append(fitted)
    best = best_record(r['records'])
    assert best['objective'] <= r['best']['objective']+1e-7
    r.update(best=best, **diagnostics(obj, data, best))
    r['timing'] = experiment.timing_and_gradient(obj, best)
    r['continuation'] = dict(scope=__doc__, source_sha256=digest(source),
                             implementation_sha256=digest(Path(__file__)), maximum_pass_budgets_s=BUDGETS,
                             roof_records=roofs, original_distance_m=json.loads(source.read_text())['distance_m'])
    target.write_text(json.dumps(r, default=serial, indent=2, allow_nan=False))
    print('POLISHED', scan, arm, mode, round(r['distance_m']), 'm',
          'converged', r['converged'], 'KKT', round(r['kkt'], 6), flush=True)
    return str(target)


def main():
    p = argparse.ArgumentParser(); p.add_argument('--scans', nargs='+', choices=experiment.SCANS, default=experiment.SCANS)
    p.add_argument('--workers', type=int, default=6); p.add_argument('--render-only', action='store_true')
    args = p.parse_args(); OUT.mkdir(exist_ok=True)
    if not args.render_only:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            jobs = [pool.submit(run, (s, a, m)) for s in args.scans for a in experiment.ARMS for m in experiment.PRECISIONS]
            for f in as_completed(jobs): f.result()
    experiment.OUT = OUT
    rows = experiment.collect(args.scans)
    for r in rows:
        assert r['continuation']['source_sha256'] == digest(SOURCE/f"{r['scan']}-{r['arm']}-{r['mode']}.json")
        assert r['continuation']['implementation_sha256'] == digest(Path(__file__))
        assert r['continuation']['maximum_pass_budgets_s'] == list(BUDGETS)
    summary = experiment.summarize(rows)
    experiment.render(rows, summary, args.scans)
    audit = dict(passed=True, cases=len(rows), scans=args.scans, scope=__doc__, summaries=summary,
                 dependencies=experiment.dependencies(), continuation_sha256=digest(Path(__file__)),
                 maximum_continuation_pass_budgets_s=BUDGETS, all_inputs_and_objectives_reconstructed=True,
                 notes=['Plots use continued fits; original results preserved in parent directory.',
                        'Location chosen by model score, not distance; unconverged results remain explicitly flagged.'])
    (OUT/'audit.json').write_text(json.dumps(audit, default=serial, indent=2, allow_nan=False))
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    main()
