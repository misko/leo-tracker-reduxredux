"""Score archived calibration initializations on identical full-scan inputs.

Check whether the two-start calibration already misses a better *unoptimized*
archived nuisance mode. No heldouts, location change, association changes or
truth-selected nuisance parameters. This probes optimization, not accuracy.
"""
import csv
import json
import numpy as np
from full_scan_cohort import HERE, SCANS, ARMS, OUT, digest, serial
from full_data_calibration import FullCalibration, INPUTS
from rf_calibration_diagnostic import CalibrationObjective


def seed_vector(obj, parameters, satellites, coefficient):
    p = np.asarray(parameters)
    totals = p[6+np.asarray(satellites)]
    common = np.mean(totals)
    if abs(common) > 10.+1e-7 or np.max(abs(totals)) > 20.+1e-7:
        raise ValueError('Calibration seed timing is outside the unchanged bounds')
    return np.r_[p[:6], common, obj.base.basis.T@(totals-common), coefficient]


def main():
    rows, summaries, sources = [], [], {}
    for scan in SCANS:
        cal = FullCalibration(scan); data = cal.data; ids = np.asarray(cal.record['satellite_indices'])
        root = INPUTS/scan/'seed-timing-v6'
        bootstrap = json.loads((root/'bootstrap.json').read_text())
        folds = [json.loads((root/'calibration-v2'/f'fold-{f}.json').read_text()) for f in range(5)]
        sources[scan] = {**cal.sources, str(root/'bootstrap.json'): digest(root/'bootstrap.json'),
            **{str(root/'calibration-v2'/f'fold-{i}.json'): digest(root/'calibration-v2'/f'fold-{i}.json') for i in range(5)}}
        for fold in folds: np.testing.assert_array_equal(fold['satellite_indices'], ids)
        for arm in ARMS:
            obj = CalibrationObjective(data, data.initial, ids, False, 60.)
            obj.center = cal.record['rf_center_hz']; obj.features = ((data.rf-obj.center)/1e9)[:, None]
            obj.likelihood.features = obj.features; obj.base.deadline = float('inf')
            baseline = cal.record['pre'][arm]
            seeds = [('full-prefit', baseline['parameters'], baseline['coefficient'])]
            seeds += [(f'fold-{i}-postfit', r['arms'][arm]['parameters'], r['arms'][arm]['coefficient']) for i, r in enumerate(folds)]
            seeds += [(f'bootstrap-{i}', r['parameters'], 0.) for i, r in enumerate(bootstrap['common_timing_trials'])]
            candidates = []
            for name, p, coefficient in seeds:
                if arm == 'zero-c': assert coefficient == 0.
                np.testing.assert_allclose(p[:2], data.initial[:2], atol=1e-12, rtol=0)
                assert max(abs(np.asarray(p)[[3, 5]])) <= 50.+1e-7
                assert abs(coefficient) <= 5000.+1e-7
                vector = seed_vector(obj, p, ids, coefficient)
                score, _ = obj.evaluate(vector)
                if name == 'full-prefit':
                    np.testing.assert_allclose(score, baseline['objective'], atol=1e-7, rtol=0)
                row = dict(scan=scan, arm=arm, seed=name, objective=float(score),
                           change_from_converged_prefit=float(score-baseline['objective']))
                rows.append(row); candidates.append(row)
            best = min(candidates, key=lambda r: r['objective'])
            summaries.append(dict(scan=scan, arm=arm, best_seed=best['seed'],
                                  initial_score_change=best['change_from_converged_prefit']))
    root = OUT/'calibration-seed-audit'; root.mkdir(exist_ok=True)
    with (root/'scores.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    report = dict(scope=__doc__, implementation_sha256=digest(HERE/'full_calibration_seed_audit.py'),
                  summaries=summaries, sources=sources, seeds_per_arm=11,
                  caveat='A worse unoptimized seed can still converge to a better mode; this is not an exhaustive optimization test.')
    (root/'audit.json').write_text(json.dumps(report, default=serial, indent=2, allow_nan=False))
    print(json.dumps(summaries, indent=2))


if __name__ == '__main__': main()
