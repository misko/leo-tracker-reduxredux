"""Bounded warm nonlinear satellite timing-prior ablation; no GPS access."""
import argparse
import json
import time
from pathlib import Path

import numpy as np
from acquisition_dot import prepare
from epoch_prior_adapter import prepare_epoch_prior
from regression_batch import digest, verify_sources

from leo.analysis.localization_fast import fit_localization_fast

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('unit')
    parser.add_argument('--arm', choices=['gaussian', 'student'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    start, cpu = time.monotonic(), time.process_time()
    frozen_path = HERE/'epoch-prior-warm-v1/sources.json'
    frozen = json.loads(frozen_path.read_text())
    verify_sources(frozen['source_sha256'])
    original_path = HERE/'regression-v1-freeze.json'
    assert digest(original_path) == original_path.with_suffix('.sha256').read_text().strip()
    verify_sources(json.loads(original_path.read_text())['source_sha256'])
    parent_path = next((HERE/'regression-v1').glob('batch-*/'+args.unit+'.json'))
    assert digest(parent_path) == frozen['parent_sha256'][args.unit]
    parent = json.loads(parent_path.read_text())
    scan, height, ports = prepare(args.unit)
    assert parent['inputs'] == scan.inputs and parent['height'] == height.input_bindings
    assert parent['observations'] == [list(p.observation_ids) for p in ports]
    state = np.asarray(parent['best']['mean'])
    fixed, precision, assignments, labels = prepare_epoch_prior(ports, state, args.arm == 'student')
    fit = fit_localization_fast(
        state, fixed, precision, lambda x: np.linalg.norm(x[:2]) <= 250.,
        max_iterations=64, deadline=start+25., degrees_of_freedom=4.)
    result = dict(
        unit=args.unit, arm=args.arm, parent_sha256=digest(parent_path),
        source_freeze_sha256=digest(frozen_path), inputs=scan.inputs, height=height.input_bindings,
        observations=parent['observations'], assignments=assignments, labels=labels,
        prior_factors=[list(p.observation_ids) for p in fixed[len(ports):]],
        variance_s2=.25, degrees_of_freedom=4 if args.arm == 'student' else None,
        initial_epoch_s=state[5+np.asarray(labels)].tolist(),
        final_epoch_s=fit.mean[5+np.asarray(labels)].tolist(),
        mean=fit.mean.tolist(), objectives=list(fit.objectives), converged=fit.converged,
        reason=fit.reason, iterations=fit.iterations,
        position_shift_m=float(1000*np.linalg.norm(fit.mean[:2]-state[:2])),
        initial_objective=parent['best']['objectives'][-1],
        seconds=time.monotonic()-start, cpu_seconds=time.process_time()-cpu,
        qualification='Warm conditional-identity diagnostic, not cold independent scan inference. '
        'Original nonlinear means, real-observation t4 scale and background unchanged. Only '
        'assigned satellite timing priors replace N(0,.25) with t4 scale=.125, same variance=.25. '
        'Heavier tails also imply tighter central curvature. Prior factors are model constraints. '
        'Different-arm fitted objectives are not model evidence or a selection criterion. No GPS.')
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    args.output.with_suffix('.sha256').write_text(digest(args.output)+'\n')
    print(json.dumps({k: result[k] for k in ['unit', 'arm', 'converged', 'reason',
                                            'position_shift_m', 'seconds']}))


if __name__ == '__main__':
    main()
