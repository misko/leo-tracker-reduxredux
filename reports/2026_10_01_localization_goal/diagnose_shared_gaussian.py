"""Fixed-state shared-error diagnostic; no position optimization or GPS access."""
import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from acquisition_dot import prepare

from leo.analysis.localization_marginal import integrate_shared_gaussian

HERE = Path(__file__).resolve().parent


def digest(path):
    return 'sha256:'+hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('unit', choices=['DS9-F001', 'DS10-F056'])
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    start = time.monotonic()
    freeze_path = HERE/'regression-v1-freeze.json'
    assert digest(freeze_path) == freeze_path.with_suffix('.sha256').read_text().strip()
    freeze = json.loads(freeze_path.read_text())
    for filename, expected in freeze['source_sha256'].items():
        assert digest(filename) == expected
    paths = list((HERE/'regression-v1').glob('batch-*/'+args.unit+'.json'))
    assert len(paths) == 1
    parent_path = paths[0]
    seal = json.loads(parent_path.with_suffix('.seal.json').read_text())
    assert digest(parent_path) == seal['prediction_sha256']
    parent = json.loads(parent_path.read_text())
    scan, height, ports = prepare(args.unit)
    assert scan.inputs == parent['inputs'] and height.input_bindings == parent['height']
    assert [list(p.observation_ids) for p in ports] == parent['observations']
    rows = []
    for fit in parent['fits']:
        if not fit['converged']:
            continue
        state = np.asarray(fit['mean'])
        assignments = [int(np.argmax(p.score_all(state))) for p in ports]
        active_epochs = sorted({5+i for p, i in zip(ports, assignments, strict=True)
                                if i < p.candidate_count})
        columns = np.asarray([2, 3, 4, *active_epochs])
        sigma = np.r_[1., np.full(len(columns)-1, .5)]
        blocks, errors = [], []
        plugin_log = 0.
        for port, index in zip(ports, assignments, strict=True):
            if index == port.candidate_count:
                continue
            prediction = port.predict_selected(state, index)
            assert prediction.eligible
            design = prediction.jacobian[:, columns]
            residual = port.observation-prediction.mean
            # Linearize f(b) around fitted b_hat, but integrate the original
            # zero-mean nuisance prior: y-f(b_hat)+J*b_hat = J*b+noise.
            zero_prior_residual = residual+design@state[columns]
            blocks.append((zero_prior_residual, design, prediction.covariance))
            chol = np.linalg.cholesky(prediction.covariance)
            white = np.linalg.solve(chol, residual)
            plugin_log += -.5*(residual.size*np.log(2*np.pi)
                               +2*np.log(np.diag(chol)).sum()+white@white)
            # Check one-coordinate prior-scale perturbations using nonlinear
            # predictions and exactly the same fixed satellite assignment.
            for column, scale in [(2, 1.), (3, .5), (4, .5), (5+index, .5)]:
                for sign in (-1, 1):
                    perturbed = state.copy()
                    perturbed[column] += sign*scale
                    nonlinear = port.predict_selected(perturbed, index)
                    if not nonlinear.eligible:
                        errors.append(dict(column=column, eligible=False))
                        continue
                    linear = prediction.mean+prediction.jacobian[:, column]*sign*scale
                    difference = nonlinear.mean-linear
                    norm = float(np.linalg.norm(np.linalg.solve(chol, difference)))
                    errors.append(dict(column=column, eligible=True, whitened_norm=norm))
        result = integrate_shared_gaussian(blocks, sigma)
        independent_log = sum(integrate_shared_gaussian([b], sigma).log_likelihood for b in blocks)
        finite_errors = [e['whitened_norm'] for e in errors if e['eligible']]
        rows.append(dict(seed_index=fit['seed_index'], signal_track_count=len(blocks),
                         background_track_count=len(ports)-len(blocks),
                         shared_nuisance_count=len(columns),
                         plugin_signal_gaussian_log_likelihood=float(plugin_log),
                         integrated_shared_signal_log_likelihood=result.log_likelihood,
                         integrated_independent_signal_log_likelihood=float(independent_log),
                         nuisance_columns=columns.tolist(),
                         conditional_nuisance_mean=result.nuisance_mean.tolist(),
                         linearity_check_count=len(errors),
                         ineligible_perturbations=sum(not e['eligible'] for e in errors),
                         maximum_whitened_linearization_error=max(finite_errors, default=None),
                         p90_whitened_linearization_error=(
                             float(np.percentile(finite_errors, 90)) if finite_errors else None)))
    output = dict(
        unit=args.unit, parent_sha256=digest(parent_path), source_sha256=digest(__file__),
        kernel_sha256=digest(HERE.parents[1]/'src/leo/analysis/localization_marginal.py'),
        inputs=scan.inputs, seconds=time.monotonic()-start, rows=rows,
        qualification=('Diagnostic only: fixed assignments from Student-t fits, Gaussian signal '
                       'blocks only, original nuisance prior, local linearization. Background '
                       'and association priors are omitted. Do not rank modes using these '
                       'partial scores. No position optimization, no GPS, '
                       'no calibrated uncertainty.'),
    )
    with args.output.open('x') as stream:
        json.dump(output, stream, indent=2, allow_nan=False)
    args.output.with_suffix('.sha256').write_text(digest(args.output)+'\n')
    print(json.dumps(output))


if __name__ == '__main__':
    main()
