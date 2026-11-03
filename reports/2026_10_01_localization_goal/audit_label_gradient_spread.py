"""Conditional label-gradient variation along the local compensated position path."""
import json
import time
from pathlib import Path

import numpy as np

from acquisition_dot import prepare
from audit_position_observability import retention
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent
started = time.monotonic()
sources = {str(Path(__file__)): digest(__file__),
           str(HERE/'audit_position_observability.py'): digest(HERE/'audit_position_observability.py')}
inputs, rows = {}, []
for unit in ['DS9-F025', 'DS10-F028', 'DS11-F018']:
    path = next((HERE/'regression-v1').glob('batch-*/'+unit+'.json'))
    assert digest(path) == json.loads(path.with_suffix('.seal.json').read_text())['prediction_sha256']
    parent = json.loads(path.read_text())
    verify_sources(parent['source_sha256'])
    verify_sources(parent['inputs'])
    sources.update(parent['source_sha256'])
    inputs[str(path)] = digest(path)
    _, _, ports = prepare(unit)
    state = np.asarray(parent['best']['mean'])
    scores = [p.score_all(state) for p in ports]
    assignments = [int(np.argmax(s)) for s in scores]
    epochs = sorted({5+i for p, i in zip(ports, assignments, strict=True) if i < p.candidate_count})
    columns = [0, 1, 2, 3, 4, *epochs]
    information = np.diag(np.r_[0., 0., 1., np.full(len(columns)-3, 4.)])
    for port, identity in zip(ports, assignments, strict=True):
        if identity == port.candidate_count:
            continue
        prediction = port.predict_selected(state, identity)
        residual = port.observation-prediction.mean
        solved = np.linalg.solve(prediction.covariance, residual)
        weight = (4+len(residual))/(4+float(residual@solved))
        j = prediction.jacobian[:, columns]
        information += weight*j.T@np.linalg.solve(prediction.covariance, j)
    local = np.vstack([np.eye(2), -np.linalg.solve(information[2:, 2:], information[2:, :2])])
    direction = np.zeros((len(state), 2))
    direction[columns] = local
    position_information = local.T@information@local
    total, tracks = np.zeros((2, 2)), []
    for track, (port, score) in enumerate(zip(ports, scores, strict=True)):
        probabilities = np.exp(score-np.max(score))
        probabilities /= probabilities.sum()
        indices = np.flatnonzero(probabilities[:-1] >= 1e-10)
        omitted = float(probabilities[:-1][probabilities[:-1] < 1e-10].sum())
        assert omitted < 1e-6
        gradients = np.zeros((len(indices)+1, 2))
        if len(indices):
            batch = port.linearize_candidates(state, indices)
            assert np.all(batch['eligible'])
            residual = port.observation-batch['means']
            solved = np.linalg.solve(batch['covariance'], residual.T).T
            weights = (4+residual.shape[1])/(4+np.sum(residual*solved, axis=1))
            directions = np.concatenate([np.broadcast_to(direction[:5], (len(indices), 5, 2)),
                                         direction[5+indices, None, :]], axis=1)
            j = np.einsum('ndi,nik->ndk', batch['jacobians'], directions)
            gradients[:-1] = weights[:, None]*np.einsum('ndk,nd->nk', j, solved)
        # Locally the catalogue-count clutter branch has zero derivative;
        # visibility discontinuities are outside this local diagnostic.
        mass = np.r_[probabilities[indices], probabilities[-1]]
        mass /= mass.sum()
        mean = mass@gradients
        spread = (gradients-mean).T@(mass[:, None]*(gradients-mean))
        total += spread
        tracks.append(dict(track=track, max_probability=float(probabilities.max()),
            clutter_probability=float(probabilities[-1]), omitted_mass=omitted,
            retained_satellite_branches=len(indices), gradient_covariance=spread.tolist()))
    ratios = retention(total, position_information)
    rows.append(dict(unit=unit, tracks=tracks, total_gradient_covariance=total.tolist(),
        reference_position_information=position_information.tolist(),
        gradient_spread_to_hard_irls_information=ratios.tolist(),
        ambiguous_tracks_below90pct=sum(t['max_probability'] < .9 for t in tracks),
        high_confidence_tracks_above99pct=sum(t['max_probability'] > .99 for t in tracks)))
verify_sources(sources)
result = dict(rows=rows, seconds=time.monotonic()-started, source_sha256=sources, input_sha256=inputs,
    qualification='Conditional label probabilities at fitted state, with incumbent epochs optimized '
    'and inactive epochs not reoptimized. Label-gradient covariance is the missing-label term '
    'in a mixture Hessian along a frozen hard-IRLS compensated position path. Its comparison '
    'to hard-IRLS curvature is diagnostic, not a full observed Hessian or calibrated uncertainty. '
    'Tiny branches truncated with retained mass renormalized; no bound on their gradient effect. '
    'No reference, geographic fitting or verified satellite labels; confidence can be wrong.')
output = HERE/'label-gradient-spread-v1.json'
with output.open('x') as stream:
    json.dump(result, stream, indent=2, allow_nan=False)
output.with_suffix('.sha256').write_text(digest(output)+'\n')
print(json.dumps(dict(seconds=result['seconds'], rows=[{k: v for k, v in r.items() if k != 'tracks'}
                                                    for r in rows]), indent=2))
