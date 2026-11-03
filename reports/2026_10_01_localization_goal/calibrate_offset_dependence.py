"""Fixed donor-only grid calibration with matched-marginal controls."""
import json
import time
from pathlib import Path

import numpy as np

from offset_grid_quadrature import prepare, logsumexp
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent
started = time.monotonic()
path = HERE/'offset-candidate-groups-v1.json'
assert digest(path) == path.with_suffix('.sha256').read_text().strip()
data = json.loads(path.read_text())
verify_sources(data['source_sha256'])
verify_sources(data['input_sha256'])
scales, probabilities = [10., 20., 35., 50., 75., 100., 150.], [.7, .85, .94, .98, .995]
units = list(dict.fromkeys(r['unit'] for r in data['rows']))
counts = {u: sum(len(r['groups']) for r in data['rows'] if r['unit'] == u) for u in units}
scores = np.zeros((len(units), len(scales), len(probabilities), 2))
max_error, completed, checks = 0., 0, []
for j, scale in enumerate(scales):
    for row in data['rows']:
        if time.monotonic()-started > 110:
            raise TimeoutError('bounded110s calibration assay; no incomplete ranking allowed')
        if not row['groups']:
            continue
        def evaluate(order):
            weights, ratios = prepare(row['groups'], row['offset_scale_hz'], row['df'], scale, order)
            result = []
            for p in probabilities:
                log_r = np.log((1-p)+p*ratios)
                result.append([float(logsumexp(weights+log_r.sum(axis=0))),
                               float(np.sum(logsumexp(weights+log_r, axis=1)))])
            return np.asarray(result)
        low, high = evaluate(8), evaluate(16)
        error = float(np.max(abs(high-low)))
        order = 16
        if error > 1e-6:
            low, high = high, evaluate(32)
            error, order = float(np.max(abs(high-low))), 32
        assert error < 1e-6, (row['unit'], row['track'], scale, error)
        max_error = max(max_error, error)
        scores[units.index(row['unit']), j] += high/counts[row['unit']]
        completed += 1
        checks.append(dict(unit=row['unit'], track=row['track'], scale=scale, order=order, error=error))
    print(json.dumps(dict(scale=scale, seconds=time.monotonic()-started)), flush=True)
folds = []
for dataset in ['DS9', 'DS10', 'DS11']:
    donor = [i for i, u in enumerate(units) if not u.startswith(dataset+'-')]
    target = [i for i, u in enumerate(units) if u.startswith(dataset+'-')]
    assert len(donor) == 8 and len(target) == 4
    fitted = []
    for arm in [0, 1]:
        objective = scores[donor, :, :, arm].mean(axis=0)
        j, k = np.unravel_index(np.argmax(objective), objective.shape)
        fitted.append(dict(scale_hz=scales[j], probability=probabilities[k],
            scale_index=int(j), probability_index=int(k),
            boundary=bool(j in [0, len(scales)-1] or k in [0, len(probabilities)-1])))
    sj, sk = fitted[0]['scale_index'], fitted[0]['probability_index']
    ij, ik = fitted[1]['scale_index'], fitted[1]['probability_index']
    rows = [dict(unit=units[i], groups=counts[units[i]],
        shared_score=float(scores[i, sj, sk, 0]),
        matched_marginal_independent_score=float(scores[i, sj, sk, 1]),
        separately_calibrated_independent_score=float(scores[i, ij, ik, 1]),
        shared_minus_matched=float(scores[i, sj, sk, 0]-scores[i, sj, sk, 1]),
        shared_minus_calibrated_control=float(scores[i, sj, sk, 0]-scores[i, ij, ik, 1])) for i in target]
    folds.append(dict(dataset=dataset, donor_units=[units[i] for i in donor],
        shared_parameters=fitted[0], independent_parameters=fitted[1], rows=rows))
sources = dict(data['source_sha256'])
for name in ['calibrate_offset_dependence.py', 'offset_grid_quadrature.py']:
    sources[str(HERE/name)] = digest(HERE/name)
verify_sources(sources)
result = dict(folds=folds, units=units, scores=scores.tolist(), checks=checks,
    scales_hz=scales, probabilities=probabilities, completed_track_scale_checks=completed,
    maximum_refinement_difference=max_error, seconds=time.monotonic()-started,
    source_sha256=sources, input_sha256={str(path): digest(path)},
    qualification='Fixed-state exploratory donor-dataset grid calibration, equal scan means. '
    'No target dataset in parameter selection. Shared versus independent-per-group offset '
    'integrals use identical one-group marginal models for matched control; independent '
    'arm also calibrated separately. Grid boundary optima retained, not retuned using targets. '
    'Raw Student offset prior assumption and selected candidate clutter model remain unverified. '
    'No GPS, location fitting, independent-recording validation or uncertainty success claim.')
output = HERE/'offset-dependence-transfer-v1.json'
with output.open('x') as stream:
    json.dump(result, stream, indent=2, allow_nan=False)
output.with_suffix('.sha256').write_text(digest(output)+'\n')
print(json.dumps(dict(folds=folds, seconds=result['seconds'], max_error=max_error), indent=2))
