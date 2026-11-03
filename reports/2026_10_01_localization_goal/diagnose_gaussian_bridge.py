"""Warm diagnostic: can Gaussian endpoints discover a better original robust mode?"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
from acquisition_dot import prepare
from regression_batch import digest, verify_sources

from leo.analysis.localization_fast import fit_localization_fast

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('unit')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    start = time.monotonic()
    freeze_path = HERE/'nonlinear-gaussian-v1-freeze.json'
    assert digest(freeze_path) == freeze_path.with_suffix('.sha256').read_text().strip()
    verify_sources(json.loads(freeze_path.read_text())['source_sha256'])
    path = HERE/'nonlinear-gaussian-v1'/(args.unit+'.json')
    assert digest(path) == json.loads(path.with_suffix('.seal.json').read_text())[
        'prediction_sha256']
    parent = json.loads(path.read_text())
    assert parent['best']['converged']
    scan, height, ports = prepare(args.unit)
    assert scan.inputs == parent['inputs'] and height.input_bindings == parent['height']
    assert [list(p.observation_ids) for p in ports] == parent['observations']
    state = np.asarray(parent['best']['mean'])
    precision = np.r_[0., 0., 1., np.full(len(state)-3, 4.)]
    fit = fit_localization_fast(
        state, ports, precision, lambda s: np.linalg.norm(s[:2]) <= 250.,
        max_iterations=64, deadline=start+25., degrees_of_freedom=4.)
    initial = min(parent['initial_fits'], key=lambda f: f['objectives'][-1])
    result = dict(unit=args.unit, parent_sha256=digest(path), source_sha256=digest(__file__),
                  seconds=time.monotonic()-start, converged=fit.converged, reason=fit.reason,
                  iterations=fit.iterations, mean=fit.mean.tolist(),
                  objectives=list(fit.objectives),
                  original_robust_objective=initial['objectives'][-1],
                  original_objective_gain=initial['objectives'][-1]-fit.objectives[-1],
                  displacement_from_original_m=float(1000*np.linalg.norm(
                      fit.mean[:2]-np.asarray(initial['mean'][:2]))),
                  qualification='Warm-start diagnostic only, not independent scan performance. '
                  'Original robust objective and free reassociation restored. No GPS read.')
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    args.output.with_suffix('.sha256').write_text(digest(args.output)+'\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('mean', 'objectives')}))


if __name__ == '__main__':
    main()
