"""Observed nonlinear robust Hessian at sealed modes; no refit or GPS."""
import argparse
import json
import time
from pathlib import Path

import numpy as np
from acquisition_dot import prepare
from regression_batch import digest, verify_sources

from leo.analysis.localization_observed import gradient_jacobian
from leo.analysis.localization_uncertainty import profiled_position_covariance

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('unit')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    start, cpu = time.monotonic(), time.process_time()
    freeze = HERE/'observed-curvature-v1/sources.json'
    verify_sources(json.loads(freeze.read_text())['source_sha256'])
    original = HERE/'regression-v1-freeze.json'
    assert digest(original) == original.with_suffix('.sha256').read_text().strip()
    verify_sources(json.loads(original.read_text())['source_sha256'])
    path = next((HERE/'regression-v1').glob('batch-*/'+args.unit+'.json'))
    assert digest(path) == json.loads(path.with_suffix('.seal.json').read_text())[
        'prediction_sha256']
    parent = json.loads(path.read_text())
    scan, height, ports = prepare(args.unit)
    assert scan.inputs == parent['inputs'] and height.input_bindings == parent['height']
    assert [list(p.observation_ids) for p in ports] == parent['observations']
    state = np.asarray(parent['best']['mean'])
    assignments = [int(np.argmax(p.score_all(state))) for p in ports]
    labels = sorted({i for p, i in zip(ports, assignments, strict=True) if i < p.candidate_count})
    columns = np.array([0, 1, 2, 3, 4, *(5+i for i in labels)])
    prior = np.diag(np.r_[0., 0., 1., np.full(len(columns)-3, 4.)])
    irls = prior.copy()
    observed = [prior.copy(), prior.copy()]
    max_gradient_error = 0.
    for port, index in zip(ports, assignments, strict=True):
        if index == port.candidate_count:
            continue
        local = np.array([0, 1, 2, 3, 4, 5+index])
        slot = np.array([np.flatnonzero(columns == i)[0] for i in local])
        prediction = port.predict_selected(state, index)
        residual = port.observation-prediction.mean
        jacobian = prediction.jacobian[:, local]
        solved = np.linalg.solve(prediction.covariance, residual)
        weight = (4+len(residual))/(4+residual@solved)
        irls[np.ix_(slot, slot)] += weight*jacobian.T@np.linalg.solve(
            prediction.covariance, jacobian)

        def gradient(values, local=local, port=port, index=index):
            trial = state.copy()
            trial[local] = values
            p = port.predict_selected(trial, index)
            if not p.eligible:
                raise ValueError('Hessian probe crosses eligibility boundary')
            r = port.observation-p.mean
            z = np.linalg.solve(p.covariance, r)
            return -(4+len(r))/(4+r@z)*p.jacobian[:, local].T@z

        # Confirm the supplied analytic gradient against the original branch score.
        direction = np.array([.3, -.2, .1, -.4, .2, -.1])
        trial_a, trial_b = state.copy(), state.copy()
        trial_a[local] += .001*direction
        trial_b[local] -= .001*direction
        finite = (-port.score_selected(trial_a, index)
                  +port.score_selected(trial_b, index))/.002
        max_gradient_error = max(max_gradient_error, abs(finite-gradient(state[local])@direction))
        for j, h in enumerate([.01, .005]):
            steps = np.full(6, h)
            observed[j][np.ix_(slot, slot)] += gradient_jacobian(gradient, state[local], steps)
    rows = []
    for name, raw in [('irls', irls), ('observed_h001', observed[0]),
                      ('observed_h0005', observed[1])]:
        matrix = .5*(raw+raw.T)
        eigen = np.linalg.eigvalsh(matrix)
        nuisance_eigen = np.linalg.eigvalsh(matrix[2:, 2:])
        row = dict(name=name, matrix=matrix.tolist(), minimum_eigenvalue=float(eigen[0]),
                   nuisance_minimum_eigenvalue=float(nuisance_eigen[0]),
                   relative_asymmetry=float(np.linalg.norm(raw-raw.T)/np.linalg.norm(raw)),
                   nuisance_logdet=None, position_axis_scales_m=None)
        if nuisance_eigen[0] > 0:
            row['nuisance_logdet'] = float(np.linalg.slogdet(matrix[2:, 2:])[1])
        if eigen[0] > 0:
            covariance = profiled_position_covariance(matrix)
            row['position_axis_scales_m'] = (1000*np.sqrt(np.linalg.eigvalsh(covariance))).tolist()
        rows.append(row)
    result = dict(
        unit=args.unit, parent_sha256=digest(path), source_freeze_sha256=digest(freeze),
        columns=columns.tolist(), assignments=assignments,
        maximum_directional_gradient_error=max_gradient_error,
        relative_hessian_refinement=float(np.linalg.norm(observed[0]-observed[1])
                                          /np.linalg.norm(observed[1])),
        rows=rows, seconds=time.monotonic()-start, cpu_seconds=time.process_time()-cpu,
        qualification='Numerically differentiated gradient of original nonlinear Student-t '
        'fixed-assignment score plus Gaussian priors. Two step sizes and symmetry audit; no PSD '
        'clipping. Background visibility is piecewise constant locally and contributes no smooth '
        'derivative. Not marginal-likelihood optimization or calibrated uncertainty. No GPS.')
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    args.output.with_suffix('.sha256').write_text(digest(args.output)+'\n')
    compact = {k: v for k, v in result.items() if k not in ['rows', 'assignments', 'columns']}
    compact['rows'] = [{k: v for k, v in r.items() if k != 'matrix'} for r in rows]
    print(json.dumps(compact, indent=2))


if __name__ == '__main__':
    main()
