"""Resolve intrinsic-noise boundary with exact odd-df convolutions."""
import json
import time
from pathlib import Path

import numpy as np

from offset_marginal_density import density, _quadrature_pdf
from calibrate_candidate_density import profile_probability
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent
started = time.monotonic()
inputs = {}
loaded = []
for name in ['offset-candidate-groups-v1.json', 'offset-dependence-transfer-v2.json',
             'candidate-density-transfer-v1.json']:
    path = HERE/name
    assert digest(path) == path.with_suffix('.sha256').read_text().strip()
    loaded.append(json.loads(path.read_text()))
    inputs[str(path)] = digest(path)
data, old_grid, old_cauchy = loaded
verify_sources(data['source_sha256'])
verify_sources(data['input_sha256'])
units = old_grid['units']
scales = [0., .25, .5, 1., 2.5, 5., 7.5, 10., 15., 20., 35., 50., 75., 100., 150.]
ratios, parity, even_error = {}, 0., 0.
for noise in scales:
    by_unit = {u: [] for u in units}
    for row in data['rows']:
        groups = row['groups']
        if not groups:
            continue
        sizes = np.array([len(g['residuals_hz']) for g in groups])
        residual = np.concatenate([g['residuals_hz'] for g in groups])
        period = groups[0]['period_hz']
        pdf = density(residual, period, row['offset_scale_hz'], row['df'], noise, derivatives=False)[0]
        if row['df'] == 10 and noise > 0:
            refined = _quadrature_pdf(residual, period, row['offset_scale_hz'], row['df'], noise, order=256)
            difference = float(np.max(abs(pdf/refined-1)))
            even_error = max(even_error, difference)
            assert difference < 1e-5
        sums = np.add.reduceat(pdf, np.r_[0, np.cumsum(sizes)[:-1]])
        by_unit[row['unit']].extend((period*sums/sizes).tolist())
    ratios[noise] = {u: np.asarray(v) for u, v in by_unit.items()}
    if noise in old_grid['scales_hz']:
        j = old_grid['scales_hz'].index(noise)
        for i, unit in enumerate(units):
            for k, p in enumerate(old_grid['probabilities']):
                score = float(np.mean(np.log1p(p*(ratios[noise][unit]-1))))
                difference = abs(score-old_grid['scores'][i][j][k][1])
                parity = max(parity, difference)
                assert difference < 1e-6
    print(json.dumps(dict(noise=noise, seconds=time.monotonic()-started)), flush=True)
baseline = {r['unit']: r for f in old_cauchy['folds'] for r in f['targets']}
folds = []
for dataset in ['DS9', 'DS10', 'DS11']:
    donors = [u for u in units if not u.startswith(dataset+'-')]
    targets = [u for u in units if u.startswith(dataset+'-')]
    grid = []
    for noise in scales:
        values = np.concatenate([ratios[noise][u] for u in donors])
        weights = np.concatenate([np.full(len(ratios[noise][u]), 1/(len(donors)*len(ratios[noise][u])))
                                  for u in donors])
        objective, probability = profile_probability(values, weights)
        grid.append(dict(noise_hz=noise, probability=probability, donor_mean_log_ratio=objective))
    chosen = max(grid, key=lambda r: r['donor_mean_log_ratio'])
    noise, p = chosen['noise_hz'], chosen['probability']
    rows = []
    for unit in targets:
        score = float(np.mean(np.log1p(p*(ratios[noise][unit]-1))))
        rows.append(dict(unit=unit, groups=len(ratios[noise][unit]), mean_log_ratio=score,
            previous_calibrated_cauchy_score=baseline[unit]['calibrated_mean_log_ratio'],
            gain=score-baseline[unit]['calibrated_mean_log_ratio']))
    folds.append(dict(dataset=dataset, donors=donors, chosen=chosen, grid=grid,
        boundary=noise in [scales[0], scales[-1]], rows=rows))
sources = dict(data['source_sha256'])
for name in ['calibrate_offset_marginal_v2.py', 'offset_marginal_density.py', 'offset_grid_quadrature.py',
             'calibrate_candidate_density.py', 'audit_candidate_count_calibration.py']:
    sources[str(HERE/name)] = digest(HERE/name)
verify_sources(sources)
verify_sources(inputs)
result = dict(folds=folds, seconds=time.monotonic()-started, noise_grid=scales,
    previous_grid_max_score_difference=parity, even_df_max_relative_refinement_difference=even_error,
    source_sha256=sources, input_sha256=inputs,
    qualification='Exploratory donor-only calibration; target dataset excluded from parameter '
    'selection. Noise grid includes physical zero limit, p profiled continuously in [.001,.999]. '
    'Each scan weighted equally. Independent offset convolution is a marginal predictive '
    'surrogate, not independent physical track offsets. No GPS, geographic fit or heldout result.')
output = HERE/'offset-marginal-calibration-v2.json'
with output.open('x') as stream:
    json.dump(result, stream, indent=2, allow_nan=False)
output.with_suffix('.sha256').write_text(digest(output)+'\n')
print(json.dumps(dict(seconds=result['seconds'], parity=parity, even_error=even_error,
    folds=[{k: v for k, v in f.items() if k != 'grid'} for f in folds]), indent=2))
