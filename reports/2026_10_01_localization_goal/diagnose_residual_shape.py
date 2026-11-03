"""Describe fixed-state residual shape without fitting locations or reading GPS."""
import argparse
import json
from pathlib import Path

import numpy as np
from acquisition_dot import prepare
from regression_batch import digest

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('unit', choices=['DS9-F001', 'DS10-F056'])
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    paths = list((HERE/'regression-v1').glob('batch-*/'+args.unit+'.json'))
    assert len(paths) == 1
    path = paths[0]
    assert digest(path) == json.loads(path.with_suffix('.seal.json').read_text())['prediction_sha256']
    receipt = json.loads(path.read_text())
    for filename, expected in receipt['source_sha256'].items():
        assert digest(filename) == expected
    scan, height, ports = prepare(args.unit)
    assert scan.inputs == receipt['inputs'] and height.input_bindings == receipt['height']
    state = np.asarray(receipt['best']['mean'])
    rows = []
    for port in ports:
        scores = port.score_all(state)
        index = int(np.argmax(scores))
        if index == port.candidate_count:
            continue
        prediction = port.predict_selected(state, index)
        residual = port.observation-prediction.mean
        chol = np.linalg.cholesky(prediction.covariance)
        white = np.linalg.solve(chol, residual)
        quadratic = float(white@white)
        likelihood = port.likelihood
        centered = likelihood.centered_times
        polynomial = likelihood.contrasts@np.column_stack((centered, centered**2))
        white_polynomial = np.linalg.solve(chol, polynomial)
        remainder = white-white_polynomial@np.linalg.lstsq(
            white_polynomial, white, rcond=1e-12)[0]
        raw_centered = likelihood.contrasts.T@residual
        raw_energy = float(raw_centered@raw_centered)
        weights = np.exp(scores-scores.max())
        weights /= weights.sum()
        rows.append(dict(
            observation_ids=list(port.observation_ids), selected_satellite=scan.bank.norad_ids[index],
            times_s=likelihood.times.tolist(), raw_centered_residual_hz=raw_centered.tolist(),
            contrast_dimension=len(residual), quadratic=quadratic,
            student_t_weight=(4+len(residual))/(4+quadratic),
            max_point_centered_energy_fraction=float(np.max(raw_centered**2)/raw_energy)
            if raw_energy else 0.,
            quadratic_removed_by_unpenalized_slope_and_curvature=(
                max(0., quadratic-float(remainder@remainder))/quadratic if quadratic else 0.),
            selected_branch_probability=float(weights[index]),
        ))
    result = dict(
        unit=args.unit, parent_sha256=digest(path), source_sha256=digest(__file__), rows=rows,
        qualification=('Fixed fitted state and selected identities; descriptive diagnostics only. '
                       'Centered raw residuals reconstruct contrasts, not absolute carrier errors. '
                       'Polynomial projection is unpenalized and is not a fitted localization arm. '
                       'Neither residual energy nor conditional branch probabilities calibrate '
                       'geographic uncertainty. No GPS accessed.'),
    )
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps(dict(unit=args.unit, tracks=len(rows),
                         low_weight_tracks=sum(r['student_t_weight'] < .5 for r in rows),
                         median_weight=float(np.median([r['student_t_weight'] for r in rows])),
                         polynomial_explained_fraction=float(np.median([
                             r['quadratic_removed_by_unpenalized_slope_and_curvature']
                             for r in rows])))))


if __name__ == '__main__':
    main()
