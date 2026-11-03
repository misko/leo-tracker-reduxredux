"""Fresh acquisition with denser fitting evidence and a total 90-second cap."""
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
from acquisition_dot import propose_dot
from dense_adapter import dense_ports, prepare
from regression_batch import digest
from leo.analysis.localization_fast import fit_localization_fast

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('unit', choices=['DS9-F001', 'DS10-F056', 'DS11-F001'])
    parser.add_argument('--max-points', required=True, type=int, choices=[8, 16])
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    result = dict(unit_id=args.unit, fits=[], status='error',
                  config=dict(prior_radius_km=250., height_m_msl=30.48,
                              acquisition_max_points=8, fit_max_points=args.max_points,
                              seed_limit=3, iterations_per_seed=64, acquisition_limit_s=50.,
                              internal_deadline_s=85., external_limit_s=90.),
                  qualification='Development pilot; denser time-spread fitting samples; no GPS')
    try:
        scan, height, acquisition_ports = prepare(args.unit)
        ports = dense_ports(scan, height, args.max_points)
        ids = [i for p in ports for i in p.observation_ids]
        if len(ids) != len(set(ids)):
            raise ValueError('duplicate physical observations')
        result.update(inputs=scan.inputs, height=height.input_bindings,
                      observations=[list(p.observation_ids) for p in ports],
                      acquisition_observations=[list(p.observation_ids) for p in acquisition_ports])
        proposal, counts = propose_dot(scan, height,
                                      deadline_s=min(50., START+80.-time.monotonic()))
        result.update(proposal=asdict(proposal), acquisition_counts=counts)
        for i, seed in enumerate(proposal.seeds[:3]):
            if time.monotonic() >= START+85.:
                break
            state = np.zeros(5+len(scan.bank.norad_ids))
            state[:2] = seed.east_km, seed.north_km
            precision = np.r_[0., 0., 1., np.full(state.size-3, 4.)]
            began = time.monotonic()
            fit = fit_localization_fast(
                state, ports, precision, lambda s: np.linalg.norm(s[:2]) <= 250.,
                max_iterations=64, deadline=START+85., degrees_of_freedom=4.)
            result['fits'].append(dict(seed_index=i, mean=fit.mean.tolist(),
                                      objectives=list(fit.objectives), reason=fit.reason,
                                      converged=fit.converged, iterations=fit.iterations,
                                      seconds=time.monotonic()-began))
        scored = [f for f in result['fits'] if f['objectives']]
        result['best'] = min(scored, key=lambda f: f['objectives'][-1]) if scored else None
        result['status'] = ('converged_local_mode' if result['best']
                            and result['best']['converged'] else 'unresolved')
    except Exception as error:
        result['exception'] = type(error).__name__+': '+str(error)
    sources = {}
    for module in tuple(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if filename:
            path = Path(filename).resolve()
            if path.suffix == '.py' and path.is_relative_to(HERE.parents[1]):
                sources[str(path)] = digest(path)
    usage = resource.getrusage(resource.RUSAGE_SELF)
    result.update(source_sha256=sources, cpu_seconds=usage.ru_utime+usage.ru_stime,
                  wall_seconds_before_sealing=time.monotonic()-START)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    args.output.with_suffix('.seal.json').write_text(json.dumps(dict(
        prediction_sha256=digest(args.output))))
    print(json.dumps({k: result.get(k) for k in
                     ['unit_id', 'status', 'wall_seconds_before_sealing', 'exception']}))


if __name__ == '__main__':
    main()
