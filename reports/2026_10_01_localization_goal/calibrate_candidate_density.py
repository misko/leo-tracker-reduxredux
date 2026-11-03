"""Leave-one-dataset-out calibration of complete admitted candidate sets."""
import json
import time
from pathlib import Path

import numpy as np

from audit_candidate_count_calibration import central_mass
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent


def pack(rows):
    samples = [s for row in rows for s in row['samples']]
    counts = np.array([s['candidate_count'] for s in samples])
    periods = np.array([s['period_hz'] for s in samples])
    residuals = np.concatenate([s['residuals_hz'] for s in samples])
    weights = np.concatenate([np.full(len(row['samples']), 1/(len(rows)*len(row['samples'])))
                              for row in rows])
    assert all(len(s['residuals_hz']) == s['candidate_count'] for s in samples)
    return dict(counts=counts, periods=periods, residuals=residuals,
                slots=np.repeat(np.arange(len(samples)), counts), weights=weights)


def signal_ratios(data, scale):
    period = data['periods'][data['slots']]
    a = 2*np.pi*scale/period
    phase = ((data['residuals']+period/2) % period-period/2)*np.pi/period
    ratios = -np.expm1(-2*a)/(np.expm1(-a)**2+4*np.exp(-a)*np.sin(phase)**2)
    return np.bincount(data['slots'], weights=ratios)/data['counts']


def profile_probability(ratios, weights):
    delta = ratios-1
    lower, upper = .001, .999
    for _ in range(48):
        middle = (lower+upper)/2
        derivative = weights@(delta/(1+middle*delta))
        if derivative > 0:
            lower = middle
        else:
            upper = middle
    p = (lower+upper)/2
    return float(weights@np.log1p(p*delta)), p


def fit(rows):
    data = pack(rows)
    grid = np.linspace(np.log(1.), np.log(2000.), 61)
    def objective(log_scale):
        return profile_probability(signal_ratios(data, np.exp(log_scale)), data['weights'])
    values = [objective(s)[0] for s in grid]
    best = int(np.argmax(values))
    lo, hi = grid[max(0, best-1)], grid[min(len(grid)-1, best+1)]
    # Bounded one-dimensional profile search, bracketed by the full fixed grid.
    for _ in range(45):
        left, right = lo+(hi-lo)/3, hi-(hi-lo)/3
        if objective(left)[0] > objective(right)[0]:
            hi = right
        else:
            lo = left
    log_scale = (lo+hi)/2
    score, probability = objective(log_scale)
    return dict(scale_hz=float(np.exp(log_scale)), signal_probability=probability,
                mean_log_ratio=score, scale_grid_boundary=best in (0, len(grid)-1),
                probability_boundary=probability < .00101 or probability > .99899)


def main():
    start = time.monotonic()
    path = HERE/'candidate-calibration-inputs-v1.json'
    assert digest(path) == path.with_suffix('.sha256').read_text().strip()
    inputs = json.loads(path.read_text())
    sources = dict(inputs['source_sha256'])
    for name in ['calibrate_candidate_density.py', 'audit_candidate_count_calibration.py']:
        sources[str(HERE/name)] = digest(HERE/name)
    verify_sources(sources)
    rows, folds = inputs['rows'], []
    for dataset in ['DS9', 'DS10', 'DS11']:
        donors = [r for r in rows if r['unit'].split('-')[0] != dataset]
        targets = [r for r in rows if r['unit'].split('-')[0] == dataset]
        assert len(donors) == 8 and len(targets) == 4
        fitted = fit(donors)
        results = []
        for row in targets:
            data = pack([row])
            base = np.log1p(.5*(signal_ratios(data, 200.)-1))
            calibrated = np.log1p(fitted['signal_probability']*
                                  (signal_ratios(data, fitted['scale_hz'])-1))
            probabilities = np.array([central_mass(abs(s['residual_hz']), s['period_hz'],
                scale=fitted['scale_hz'], probability=fitted['signal_probability'],
                candidate_count=s['candidate_count']) for s in row['samples']])
            results.append(dict(unit=row['unit'], groups=len(base), all_groups=row['all_groups'],
                mean_log_ratio_gain=float(np.mean(calibrated-base)),
                baseline_mean_log_ratio=float(np.mean(base)),
                calibrated_mean_log_ratio=float(np.mean(calibrated)),
                baseline_coverage=row['coverage'],
                calibrated_coverage={str(q): float(np.mean(probabilities <= q)) for q in [.5, .9, .95]},
                central_probabilities=probabilities.tolist()))
        folds.append(dict(target_dataset=dataset, donor_units=[r['unit'] for r in donors],
            fitted=fitted, targets=results,
            mean_scan_log_ratio_gain=float(np.mean([r['mean_log_ratio_gain'] for r in results]))))
    verify_sources(sources)
    output = HERE/'candidate-density-transfer-v1.json'
    result = dict(folds=folds, input_sha256={str(path): digest(path)}, source_sha256=sources,
        seconds=time.monotonic()-start,
        protocol=dict(scale_bounds_hz=[1, 2000], probability_bounds=[.001, .999],
                      grid_points=61, weighting='equal scan means',
                      eligibility='one active prediction, nonempty candidate set'),
        qualification='Exploratory leave-dataset-out transfer on exposed development scans. '
        'No target observations enter parameter fitting. Complete admitted candidate sets are '
        'scored once per group; likelihood remains a surrogate assuming uniform independent '
        'clutter alternatives. Training states/identities/offsets are plug-in estimates. '
        'No GPS used, no geographic refit, no new uncertainty or independent-recording claim.')
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps(dict(seconds=result['seconds'], folds=[dict(
        dataset=f['target_dataset'], fitted=f['fitted'], gain=f['mean_scan_log_ratio_gain'],
        targets=[{k: v for k, v in r.items() if k != 'central_probabilities'} for r in f['targets']])
        for f in folds]), indent=2))


if __name__ == '__main__':
    main()
