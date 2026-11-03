"""Cold nonlinear control for the fixed-assignment Gaussian profile pilot."""
# ruff: noqa: E402, I001
import time

START = time.monotonic()
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import resource
import sys

import numpy as np
from acquisition_dot import prepare, propose_dot
from nonlinear_gaussian_adapter import FixedGaussianPort
from regression_batch import digest
from leo.analysis.localization_fast import fit_localization_fast

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('unit')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    result = dict(unit_id=args.unit, arm='nonlinear_gaussian', status='error',
                  initial_fits=[], fits=[], best=None, config=dict(
                      prior_radius_km=250., height_m_msl=30.48, seed_limit=3,
                      iterations_per_seed=64, acquisition_limit_s=50.,
                      initializer_deadline_s=60., internal_deadline_s=85., external_limit_s=90.,
                      gaussian_covariance_scale=2., assignments='fixed_from_initializer',
                      nuisance_model='nonlinear'),
                  qualification='Cold scan; nonlinear Gaussian signal, original nuisance priors, '
                                'fixed identities and nominal-nuisance Student-t background. '
                                'No GPS.')
    try:
        scan, height, ports = prepare(args.unit)
        result.update(inputs=scan.inputs, height=height.input_bindings,
                      observations=[list(p.observation_ids) for p in ports])
        proposal, counts = propose_dot(scan, height, deadline_s=min(
            50., START+55.-time.monotonic()))
        result.update(proposal=asdict(proposal), acquisition_counts=counts)
        for i, seed in enumerate(proposal.seeds[:3]):
            if time.monotonic() >= START+60.:
                break
            state = np.zeros(5+len(scan.bank.norad_ids))
            state[:2] = seed.east_km, seed.north_km
            precision = np.r_[0., 0., 1., np.full(state.size-3, 4.)]
            fit = fit_localization_fast(
                state, ports, precision, lambda s: np.linalg.norm(s[:2]) <= 250.,
                max_iterations=64, deadline=START+60., degrees_of_freedom=4.)
            result['initial_fits'].append(dict(
                seed_index=i, mean=fit.mean.tolist(), objectives=list(fit.objectives),
                reason=fit.reason, converged=fit.converged, iterations=fit.iterations))
        candidates = [f for f in result['initial_fits'] if f['objectives']]
        initial = min(candidates, key=lambda f: f['objectives'][-1]) if candidates else None
        if not initial or not initial['converged']:
            raise ValueError('lowest-objective initialization has not converged')
        state = np.asarray(initial['mean'])
        assigned = [int(np.argmax(p.score_all(state))) for p in ports]
        fixed = [FixedGaussianPort(p, i) for p, i in zip(ports, assigned, strict=True)]
        result.update(assignments=assigned, initializer_seed=initial['seed_index'])
        fit = fit_localization_fast(
            state, fixed, precision, lambda s: np.linalg.norm(s[:2]) <= 250.,
            max_iterations=64, deadline=START+85., degrees_of_freedom=None)
        result['best'] = dict(seed_index=initial['seed_index'], mean=fit.mean.tolist(),
                              objectives=list(fit.objectives), reason=fit.reason,
                              converged=fit.converged, iterations=fit.iterations)
        result['fits'] = [result['best']]
        result['status'] = 'converged_local_mode' if fit.converged else 'unresolved'
    except Exception as error:
        result['exception'] = type(error).__name__+': '+str(error)
    result['source_sha256'] = {}
    for module in tuple(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if filename:
            path = Path(filename).resolve()
            if path.suffix == '.py' and path.is_relative_to(HERE.parents[1]):
                result['source_sha256'][str(path)] = digest(path)
    usage = resource.getrusage(resource.RUSAGE_SELF)
    result.update(cpu_seconds=usage.ru_utime+usage.ru_stime,
                  wall_seconds_before_sealing=time.monotonic()-START)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    args.output.with_suffix('.seal.json').write_text(json.dumps(dict(
        prediction_sha256=digest(args.output))))
    print(json.dumps({k: result.get(k) for k in
                     ['unit_id', 'status', 'wall_seconds_before_sealing', 'exception']}))


if __name__ == '__main__':
    main()
