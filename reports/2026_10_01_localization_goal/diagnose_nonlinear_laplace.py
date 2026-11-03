"""One local Laplace-score position proposal, nuisance refit, no GPS selection."""
import argparse
import json
import time
from pathlib import Path

import numpy as np
from acquisition_dot import prepare
from nonlinear_laplace_adapter import FixedNuisancePort, laplace_score, observed_information
from regression_batch import digest, verify_sources

from leo.analysis.localization_fast import fit_localization_fast

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('unit')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    start, cpu = time.monotonic(), time.process_time()
    freeze_path = HERE/'nonlinear-laplace-warm-v1/sources.json'
    verify_sources(json.loads(freeze_path.read_text())['source_sha256'])
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
    information = observed_information(ports, assignments, state, columns)
    np.linalg.cholesky(information)
    tangent = -np.linalg.solve(information[2:, 2:], information[2:, :2])
    schur = information[:2, :2]+information[:2, 2:]@tangent
    gradients = []
    for h in [.1, .05]:
        gradient = np.zeros(2)
        for axis in range(2):
            values = []
            for sign in [-1, 1]:
                delta = np.eye(2)[axis]*h*sign
                trial = state.copy()
                trial[:2] += delta
                trial[columns[2:]] += tangent@delta
                nuisance = observed_information(ports, assignments, trial, columns[2:])
                chol = np.linalg.cholesky(nuisance)
                values.append(float(np.log(np.diag(chol)).sum()))
            gradient[axis] = (values[1]-values[0])/(2*h)
        gradients.append(gradient)
    proposed = -np.linalg.solve(schur, gradients[-1])
    unbounded_step = proposed.copy()
    if np.linalg.norm(proposed) > 2.:
        proposed *= 2./np.linalg.norm(proposed)
    trial = state.copy()
    trial[:2] += proposed
    trial[columns[2:]] += tangent@proposed
    precision = np.r_[0., 0., 1., np.full(len(state)-3, 4.)]
    fixed = [FixedNuisancePort(p, i, trial[:2]) for p, i in zip(ports, assignments, strict=True)]
    fit = fit_localization_fast(
        trial, fixed, precision, lambda s: np.linalg.norm(s[:2]) <= 250.,
        max_iterations=64, deadline=start+45., degrees_of_freedom=4.)
    np.testing.assert_allclose(fit.mean[:2], trial[:2], atol=1e-10, rtol=0)
    baseline = laplace_score(ports, assignments, state, columns[2:])
    candidate = laplace_score(ports, assignments, fit.mean, columns[2:])
    changes = sum(int(np.argmax(p.score_all(fit.mean))) != i
                  for p, i in zip(ports, assignments, strict=True))
    refinement = float(np.linalg.norm(gradients[0]-gradients[1]))
    numerical_ok = refinement <= max(.001, .02*np.linalg.norm(gradients[-1]))
    accepted = bool(fit.converged and changes == 0 and numerical_ok and candidate[0] < baseline[0])
    result = dict(
        unit=args.unit, parent_sha256=digest(path), source_freeze_sha256=digest(freeze_path),
        inputs=scan.inputs, height=height.input_bindings, observations=parent['observations'],
        assignments=assignments, columns=columns.tolist(),
        half_logdet_position_gradients=[g.tolist() for g in gradients],
        gradient_refinement_norm=refinement, numerical_ok=bool(numerical_ok),
        unbounded_step_km=unbounded_step.tolist(), proposed_step_km=proposed.tolist(),
        profile_information=schur.tolist(), baseline_score_profile_logdet=list(baseline),
        candidate_score_profile_logdet=list(candidate),
        nuisance_converged=fit.converged, nuisance_reason=fit.reason, iterations=fit.iterations,
        assignment_changes=changes, candidate_mean=fit.mean.tolist(),
        candidate_accepted=accepted, selected_mean=(fit.mean if accepted else state).tolist(),
        cpu_seconds=time.process_time()-cpu, seconds=time.monotonic()-start,
        qualification='Warm one-step local nonlinear Laplace approximation, fixed identity mode. '
        'Position gradient of half nuisance log determinant along conditional-mode tangent; '
        'profile Hessian supplies a capped2km proposal, then nuisance variables refit at fixed '
        'position. Two position probe sizes; unchanged original nonlinear robust likelihood. '
        'Not full marginal optimization, cold inference, or uncertainty calibration. No GPS.')
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    args.output.with_suffix('.sha256').write_text(digest(args.output)+'\n')
    print(json.dumps({k: result[k] for k in ['unit', 'candidate_accepted', 'nuisance_converged',
                                            'proposed_step_km', 'gradient_refinement_norm',
                                            'assignment_changes', 'seconds']}))


if __name__ == '__main__':
    main()
