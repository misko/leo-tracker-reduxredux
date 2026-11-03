"""Cold robust acquisition followed by matched profile/marginal position fits."""
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
from marginal_position_adapter import SharedPositionObjective
from regression_batch import digest

from leo.analysis.localization_fast import fit_localization_fast
from leo.analysis.localization_position_search import fit_position_objective

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('unit')
    parser.add_argument('--arm', required=True, choices=['profile', 'marginal'])
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    config = dict(prior_radius_km=250., height_m_msl=30.48, seed_limit=3,
                  iterations_per_seed=64, acquisition_limit_s=50.,
                  initializer_deadline_s=60., internal_deadline_s=85., external_limit_s=90.,
                  position_iterations=16, difference_step_km=.05,
                  decrement_tolerance=1e-6, gaussian_covariance_scale=2.,
                  nuisance_linearization='zero_at_each_position',
                  assignments='fixed_from_initializer')
    result = dict(unit_id=args.unit, arm=args.arm, config=config, status='error',
                  initial_fits=[], fits=[], best=None,
                  qualification='Cold scan; fixed identity, linear Gaussian nuisance model. '
                                'No GPS used. Profile arm differs only by determinant correction.')
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
        model = SharedPositionObjective(ports, len(state), assigned, args.arm)
        result.update(assignments=assigned, initializer_seed=initial['seed_index'])
        fit = fit_position_objective(
            state[:2], model, lambda p: np.linalg.norm(p) <= 250., deadline=START+85.)
        # A converged fit has already evaluated its terminal position. The cache
        # avoids an unbudgeted post-fit numerical evaluation.
        cached = model.cache.get(fit.position.tobytes())
        if cached is None:
            raise ValueError('terminal position has no completed objective evaluation')
        result['best'] = dict(
            seed_index=initial['seed_index'], mean=cached[1].tolist(),
            objectives=list(fit.objectives), reason=fit.reason,
            converged=fit.converged, iterations=fit.iterations)
        result['fits'] = [result['best']]
        result['objective_evaluations'] = len(model.cache)
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
                     ['unit_id', 'arm', 'status', 'wall_seconds_before_sealing', 'exception']}))


if __name__ == '__main__':
    main()
