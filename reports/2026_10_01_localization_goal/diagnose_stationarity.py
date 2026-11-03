"""Reference-blind scaled stationarity checks at sealed regression predictions."""
import argparse
import json
import time
from pathlib import Path

import numpy as np
from acquisition_dot import prepare
from regression_batch import digest

HERE = Path(__file__).resolve().parent


def scaled_step(information, rhs):
    """Diagonal equilibration preserves the quadratic and its decrement."""
    scale = 1 / np.sqrt(np.diag(information))
    matrix = scale[:, None] * information * scale[None, :]
    chol = np.linalg.cholesky(matrix)
    whitened = np.linalg.solve(chol, scale * rhs)
    step = scale * np.linalg.solve(chol.T, whitened)
    return step, float(whitened @ whitened), float(np.linalg.cond(matrix))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('unit')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    start = time.monotonic()
    paths = list((HERE/'regression-v1').glob('batch-*/'+args.unit+'.json'))
    assert len(paths) == 1
    path = paths[0]
    assert digest(path) == json.loads(path.with_suffix('.seal.json').read_text())[
        'prediction_sha256']
    receipt = json.loads(path.read_text())
    for filename, expected in receipt['source_sha256'].items():
        assert digest(filename) == expected
    scan, height, ports = prepare(args.unit)
    assert scan.inputs == receipt['inputs'] and height.input_bindings == receipt['height']
    assert [list(p.observation_ids) for p in ports] == receipt['observations']
    state = np.asarray(receipt['best']['mean'])
    assigned = [int(np.argmax(p.score_all(state))) for p in ports]
    predictions = [(p, p.predict_selected(state, i)) for p, i in zip(ports, assigned, strict=True)
                   if i < p.candidate_count]
    active = set(map(int, np.flatnonzero(state)))
    for _, prediction in predictions:
        assert prediction.eligible
        active.update(map(int, np.flatnonzero(np.any(prediction.jacobian != 0., axis=0))))
    columns = np.array(sorted(active))
    precision = np.r_[0., 0., 1., np.full(state.size-3, 4.)]
    information = np.diag(precision[columns])
    rhs = -precision[columns] * state[columns]
    for port, prediction in predictions:
        residual = port.observation-prediction.mean
        jacobian = prediction.jacobian[:, columns]
        solved = np.linalg.solve(prediction.covariance, residual)
        weight = (4+len(residual))/(4+float(residual@solved))
        information += weight*jacobian.T@np.linalg.solve(prediction.covariance, jacobian)
        rhs += weight*jacobian.T@solved
    step, decrement, condition = scaled_step(information, rhs)
    unscaled = np.linalg.lstsq(information, rhs, rcond=1e-12)[0]

    def objective(x):
        return float(.5*np.dot(precision*x, x)-sum(
            p.score_selected(x, i) for p, i in zip(ports, assigned, strict=True)))

    # A directional derivative checks gradient consistency, including terms
    # potentially omitted by an IRLS approximation. No optimization is performed.
    direction = np.zeros_like(state)
    direction[columns] = step/max(np.sqrt(decrement), 1e-12)
    epsilon = 1e-3
    finite_difference = (objective(state+epsilon*direction)
                         - objective(state-epsilon*direction))/(2*epsilon)
    trial = state.copy()
    trial[columns] += step
    result = dict(
        unit=args.unit, receipt_sha256=digest(path), source_sha256=digest(__file__),
        winning_reason=receipt['best']['reason'], active_dimension=len(columns),
        irls_decrement_squared=decrement, equilibrated_condition=condition,
        raw_condition=float(np.linalg.cond(information)),
        proposed_position_step_m=float(1000*np.linalg.norm(step[np.isin(columns, [0, 1])])),
        unscaled_vs_scaled_step_norm=float(np.linalg.norm(unscaled-step)),
        analytic_directional_derivative=float(-rhs@direction[columns]),
        finite_difference_directional_derivative=finite_difference,
        fixed_assignment_objective_gain=objective(state)-objective(trial),
        seconds=time.monotonic()-start,
        qualification='Posthoc fixed-state diagnostic, not a new benchmark prediction. '
                      'IRLS decrement is coordinate-invariant but not an exact Newton decrement. '
                      'No reference location read. Trial is evaluated without refitting '
                      'or reassociation.')
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
