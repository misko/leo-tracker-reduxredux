"""Development pilot: full fresh acquisition and fitting within external 90 s."""
# ruff: noqa: E402, I001
import time

START = time.monotonic()
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import resource
import sys

import numpy as np

from acquisition_dot import prepare, propose_dot
from leo.analysis.localization_batched import fit_batched_soft
from leo.analysis.localization_fast import fit_localization_fast

HERE = Path(__file__).resolve().parent


def digest(path):
    return 'sha256:'+hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('unit')
    parser.add_argument('--arm', choices=['hard', 'soft'], required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists() or output.with_suffix('.seal.json').exists():
        raise FileExistsError(output)
    result = dict(schema='localization-fast-pipeline-pilot/v1', unit_id=args.unit,
                  arm=args.arm, status='error', fits=[],
                  qualification='single-scan development pilot; no GPS used in inference',
                  config=dict(prior_radius_km=250., height_m_msl=30.48, seed_limit=3,
                              iterations_per_seed=64, acquisition_limit_s=50.,
                              internal_deadline_s=85., external_limit_s=90.))
    try:
        scan, height, ports = prepare(args.unit)
        result.update(inputs=scan.inputs, height=height.input_bindings,
                      observations=[list(p.observation_ids) for p in ports])
        proposal, counts = propose_dot(
            scan, height, deadline_s=min(50., START+80.-time.monotonic()),
        )
        result.update(proposal=asdict(proposal), acquisition_counts=counts)
        solver = fit_localization_fast if args.arm == 'hard' else fit_batched_soft
        for i, seed in enumerate(proposal.seeds[:3]):
            if time.monotonic() >= START+85.:
                break
            state = np.zeros(5+len(scan.bank.norad_ids))
            state[:2] = seed.east_km, seed.north_km
            precision = np.r_[0., 0., 1., np.full(state.size-3, 4.)]
            started = time.monotonic()
            fit = solver(state, ports, precision, lambda s: np.linalg.norm(s[:2]) <= 250.,
                         max_iterations=64, deadline=START+85., degrees_of_freedom=4.)
            result['fits'].append(dict(seed_index=i, mean=fit.mean.tolist(),
                                      objectives=list(fit.objectives), reason=fit.reason,
                                      converged=fit.converged, iterations=fit.iterations,
                                      seconds=time.monotonic()-started))
        scored = [f for f in result['fits'] if f['objectives']]
        best = min(scored, key=lambda f: f['objectives'][-1]) if scored else None
        result['best'] = best
        result['status'] = 'converged_local_mode' if best and best['converged'] else 'unresolved'
    except Exception as error:
        result['exception'] = type(error).__name__+': '+str(error)
    result['source_sha256'] = {}
    for module in tuple(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if filename:
            source = Path(filename).resolve()
            if source.suffix == '.py' and source.is_relative_to(HERE.parents[1]):
                result['source_sha256'][str(source)] = digest(source)
    usage = resource.getrusage(resource.RUSAGE_SELF)
    result['cpu_seconds'] = usage.ru_utime+usage.ru_stime
    result['wall_seconds_before_sealing'] = time.monotonic()-START
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    with output.with_suffix('.seal.json').open('x') as stream:
        json.dump(dict(prediction_sha256=digest(output)), stream)
    print(json.dumps({k: result[k] for k in
                      ('unit_id', 'arm', 'status', 'wall_seconds_before_sealing')}))


if __name__ == '__main__':
    main()
