"""Fixed-state local IRLS geometry diagnostic; no GPS or refitting.

The reported inverse-curvature scales are not calibrated position uncertainty.
They condition on the fitted state and local mixture responsibilities.
"""
# ruff: noqa: E402, I001
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / '2026_10_01_localization_approaches'))
from adapter import prepare
from leo.analysis.localization_linear import student_t_branch_quadratics


def digest(path):
    return 'sha256:'+hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('receipt')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    started = time.monotonic()
    output = Path(args.output)
    if output.exists():
        raise FileExistsError(output)
    path = Path(args.receipt)
    if digest(path) != json.loads(path.with_suffix('.seal.json').read_text())['prediction_sha256']:
        raise ValueError('receipt seal mismatch')
    receipt = json.loads(path.read_text())
    for filename, expected in receipt['inputs'].items():
        if digest(filename) != expected:
            raise ValueError('changed input')
    scan, _, ports = prepare(receipt['unit_id'])
    state = np.asarray(receipt['best']['mean'])
    a, b, d = np.zeros((5, 5)), np.zeros((5, state.size-5)), np.zeros(state.size-5)
    tracks = []
    for port in ports:
        scores = port.score_all(state)
        weights = np.exp(scores-scores.max())
        weights /= weights.sum()
        indices = np.flatnonzero(weights[:-1] > 0)
        batch = port.linearize_candidates(state, indices)
        eligible = batch['eligible']
        if np.any(weights[indices[~eligible]] > 1e-15):
            raise ValueError('positive ineligible branch')
        indices = indices[eligible]
        matrices, _ = student_t_branch_quadratics(
            port.observation-batch['means'][eligible], batch['jacobians'][eligible],
            batch['covariance'], weights[indices],
        )
        a += matrices[:, :5, :5].sum(axis=0)
        b[:, indices] += matrices[:, :5, 5].T
        d[indices] += matrices[:, 5, 5]
        tracks.append(dict(background_probability=float(weights[-1]),
                           strongest_satellite_probability=float(weights[:-1].max())))
    cases = []
    for multiplier in (.25, 1., 4.):
        prior = np.r_[0., 0., 1., 4., 4.] * multiplier
        shared = a+np.diag(prior)-(b/(d+4.*multiplier))@b.T
        position = shared[:2, :2]-shared[:2, 2:]@np.linalg.solve(
            shared[2:, 2:], shared[2:, :2])
        position = (position+position.T)*.5
        eigenvalues, eigenvectors = np.linalg.eigh(position)
        cases.append(dict(nuisance_precision_multiplier=multiplier,
                          position_information_per_km2=position.tolist(),
                          eigenvalues=eigenvalues.tolist(),
                          inverse_curvature_axis_scales_m=(
                              (1000/np.sqrt(eigenvalues)).tolist()
                              if np.all(eigenvalues > 0) else None),
                          weak_direction_east_north=eigenvectors[:, 0].tolist()))
    result = dict(unit_id=receipt['unit_id'], receipt_sha256=digest(path),
                  qualification='fixed-state IRLS geometry only, not calibrated confidence',
                  no_reference_positions_read=True, no_refit=True, cases=cases, tracks=tracks,
                  seconds=time.monotonic()-started)
    result['source_sha256'] = {str(Path(__file__).resolve()): digest(__file__)}
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps(dict(unit=result['unit_id'], cases=cases, seconds=result['seconds'])))


if __name__ == '__main__':
    main()
