"""Fresh single-scan pilot, externally capped at 90 seconds including setup.

Never reads reference positions. No continuation. A completed pilot is not
automatically admitted to a frozen benchmark.
"""
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

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / '2026_10_01_localization_approaches'
sys.path.insert(0, str(PREVIOUS))
from adapter import prepare, propose
from leo.analysis.localization_batched import fit_batched_soft


def digest(path):
    return 'sha256:'+hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('unit')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists() or output.with_suffix('.seal.json').exists():
        raise FileExistsError(output)
    result = dict(schema='localization-goal-pilot/v1', unit_id=args.unit,
                  status='error', fits=[], qualification='fresh single-scan development pilot',
                  config=dict(prior_radius_km=250., height_m_msl=30.48,
                              iterations_per_seed=64, seed_limit=3,
                              acquisition_limit_s=50., internal_deadline_s=85.,
                              required_external_timeout_s=90.))
    try:
        scan, height, ports = prepare(args.unit)
        result.update(inputs=scan.inputs, height=height.input_bindings,
                      observations=[list(p.observation_ids) for p in ports])
        started = time.monotonic()
        proposal = propose(scan, height, max_tracks=len(scan.tracks),
                           deadline_s=min(50., max(0., START+80.-started)),
                           degrees_of_freedom=4.)
        result['acquisition_seconds'] = time.monotonic()-started
        result['proposal'] = asdict(proposal)
        for i, seed in enumerate(proposal.seeds[:3]):
            if time.monotonic() >= START+85.:
                break
            state = np.zeros(5+len(scan.bank.norad_ids))
            state[:2] = seed.east_km, seed.north_km
            precision = np.r_[0., 0., 1., np.full(state.size-3, 4.)]
            started = time.monotonic()
            fit = fit_batched_soft(state, ports, precision,
                                   lambda s: np.linalg.norm(s[:2]) <= 250.,
                                   max_iterations=64, deadline=START+85.)
            result['fits'].append(dict(seed_index=i, mean=fit.mean.tolist(),
                                      objectives=list(fit.objectives), reason=fit.reason,
                                      converged=fit.converged, iterations=fit.iterations,
                                      fit_seconds=time.monotonic()-started))
        scored = [f for f in result['fits'] if f['objectives']]
        best = min(scored, key=lambda f: f['objectives'][-1]) if scored else None
        result['best'] = best
        result['status'] = 'converged_local_mode' if best and best['converged'] else 'unresolved'
    except Exception as error:
        result['exception'] = type(error).__name__+': '+str(error)
    root = HERE.parents[1]
    result['source_sha256'] = {}
    for module in tuple(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if filename:
            path = Path(filename).resolve()
            if path.suffix == '.py' and path.is_relative_to(root):
                result['source_sha256'][str(path)] = digest(path)
    result['wall_seconds_before_sealing'] = time.monotonic()-START
    usage = resource.getrusage(resource.RUSAGE_SELF)
    result['cpu_seconds'] = usage.ru_utime+usage.ru_stime
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    with output.with_suffix('.seal.json').open('x') as stream:
        json.dump(dict(prediction_sha256=digest(output)), stream)
    print(json.dumps({k: result[k] for k in ('unit_id', 'status', 'wall_seconds_before_sealing')}))


if __name__ == '__main__':
    main()
