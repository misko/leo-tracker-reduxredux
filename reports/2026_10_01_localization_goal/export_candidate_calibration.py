"""Check frozen training-only predictions; no localization or parameter fitting."""
import json
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from score_checking_expansion import mode_predictions, prepare
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent


def central_mass(width, period, scale=200., probability=.5, candidate_count=1):
    """CDF of nearest absolute residual, conditional on candidate count."""
    width = np.asarray(width)
    signal = 2/np.pi*np.arctan(np.tan(np.pi*width/period)
                              /np.tanh(np.pi*scale/period))
    uniform = 2*width/period
    return 1-((1-probability)*(1-uniform)**candidate_count
              + probability*(1-signal)*(1-uniform)**(candidate_count-1))


def main():
    started = time.monotonic()
    freeze = HERE/'split-expansion-fit-v1/sources.json'
    assert digest(freeze) == freeze.with_suffix('.sha256').read_text().strip()
    frozen = json.loads(freeze.read_text())
    sources = dict(frozen['source_sha256'])
    for path in [Path(__file__), HERE/'score_checking_expansion.py']:
        sources[str(path)] = digest(path)
    verify_sources(sources)
    parents, rows = {}, []
    for unit in frozen['units']:
        path = freeze.parent/(unit+'.json')
        assert digest(path) == json.loads(path.with_suffix('.seal.json').read_text())['prediction_sha256']
        receipt = json.loads(path.read_text())
        verify_sources(receipt['inputs'])
        source_path = HERE/'source-split-expansion-v1'/(unit+'.json')
        assert digest(source_path) == source_path.with_suffix('.sha256').read_text().strip()
        parents[str(path)], parents[str(source_path)] = digest(path), digest(source_path)
        source = json.loads(source_path.read_text())
        grouped = defaultdict(list)
        for point in source['checking_points']:
            grouped[point['source_group_id']].append(point)
        groups = []
        for key, points in sorted(grouped.items()):
            first = points[0]
            scale = 11.2e9/first['actual_rf_hz']
            groups.append(dict(source_group_id=key, receiver=first['receiver_id'],
                channel=first['channel'], visit=first['visit_index'], rf_hz=first['actual_rf_hz'],
                time_s=float(np.median([(p['support_center_utc_ns']-source['start_utc_ns'])/1e9
                                        for p in points])),
                candidates=[p['measured_cfo_hz']*scale for p in points],
                period=scale/4.4e-6))
        scan, height, ports = prepare(unit)
        best = next(f for f in receipt['fits'] if f['seed_index'] == receipt['best']['seed_index'])
        assert best['converged']
        predictions, parity, _ = mode_predictions(scan, height, ports, np.asarray(best['mean']), groups)
        samples = []
        visits = defaultdict(list)
        for group, means in zip(groups, predictions, strict=True):
            if len(means) != 1 or not group['candidates']:
                continue
            period = group['period']
            residuals = (np.asarray(group['candidates'])-means[0]+period/2) % period-period/2
            residual = float(residuals[np.argmin(abs(residuals))])
            sample = dict(source_group_id=group['source_group_id'], residual_hz=residual,
                          period_hz=period, candidate_count=len(group['candidates']), residuals_hz=residuals.tolist(),
                          central_probability=float(central_mass(abs(residual), period,
                              candidate_count=len(group['candidates']))))
            samples.append(sample)
            visits[(group['receiver'], group['channel'], group['visit'])].append((group['time_s'], residual))
        agree, count, null = 0, 0, 0.
        rng = np.random.default_rng(20261001)
        for values in visits.values():
            values = np.asarray(sorted(values))
            if len(values) < 2:
                continue
            mask = (np.diff(values[:, 0]) > 0) & (np.diff(values[:, 0]) <= .25)
            signs = values[:, 1] > 0
            agree += int(np.sum((signs[1:] == signs[:-1]) & mask))
            count += int(mask.sum())
            for _ in range(100):
                permuted = rng.permutation(signs)
                null += np.sum((permuted[1:] == permuted[:-1]) & mask)/100
        probabilities = np.array([s['central_probability'] for s in samples])
        residuals = np.array([abs(s['residual_hz']) for s in samples])
        rows.append(dict(unit=unit, all_groups=len(groups), single_prediction_groups=len(samples),
            coverage={str(q): float(np.mean(probabilities <= q)) for q in [.5, .9, .95]},
            residual_quantiles_hz={str(q): float(np.quantile(residuals, q)) for q in [.5, .9, .95]},
            within_hz={str(w): float(np.mean(residuals <= w)) for w in [200, 600, 2000]},
            adjacent_pairs=count, adjacent_sign_agreements=agree,
            within_visit_shuffled_expected_agreements=float(null), training_mean_parity_hz=parity,
            samples=samples))
    verify_sources(sources)
    verify_sources(parents)
    result = dict(rows=rows, source_sha256=sources, input_sha256=parents,
        seconds=time.monotonic()-started,
        qualification='Training-winner predictions only; checking observations never refitted. '
        'Conditional on admitted peak count and exactly one active prediction; excluded groups retained '
        'in counts. This diagnoses the assumed candidate model, not absolute CFO truth, satellite '
        'identity, position uncertainty, or unseen-recording performance. Shared training states '
        'and trajectory selection affect residuals. Permutation is descriptive, not an iid test. '
        'No GPS, new RF, localization fits, or changes to baseline.')
    output = HERE/'candidate-calibration-inputs-v1.json'
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps(dict(seconds=result['seconds'], rows=[{k: v for k, v in r.items()
        if k != 'samples'} for r in rows]), indent=2))


if __name__ == '__main__':
    main()
