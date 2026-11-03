"""Matched baseline and rare raw-sample scale mixture, bounded warm fits."""
import argparse
import json
import time
from pathlib import Path

import numpy as np
from acquisition_dot import prepare
from regression_batch import digest, verify_sources
from sample_mixture_adapter import SampleMixturePort

from leo.analysis.localization_fast import fit_localization_fast

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('unit')
    parser.add_argument('--arm', choices=['control', 'mixture'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    start, cpu = time.monotonic(), time.process_time()
    frozen = HERE/'sample-mixture-v1/sources.json'
    verify_sources(json.loads(frozen.read_text())['source_sha256'])
    original = HERE/'regression-v1-freeze.json'
    assert digest(original) == original.with_suffix('.sha256').read_text().strip()
    verify_sources(json.loads(original.read_text())['source_sha256'])
    path = next((HERE/'regression-v1').glob('batch-*/'+args.unit+'.json'))
    seal = json.loads(path.with_suffix('.seal.json').read_text())
    assert digest(path) == seal['prediction_sha256']
    parent = json.loads(path.read_text())
    scan, height, ports = prepare(args.unit)
    assert scan.inputs == parent['inputs'] and height.input_bindings == parent['height']
    assert [list(p.observation_ids) for p in ports] == parent['observations']
    state = np.asarray(parent['best']['mean'])
    assignments = [int(np.argmax(p.score_all(state))) for p in ports]
    probability = 0. if args.arm == 'control' else .05
    adapted = [SampleMixturePort(p, i, probability)
               for p, i in zip(ports, assignments, strict=True)]
    precision = np.r_[0., 0., 1., np.full(len(state)-3, 4.)]
    # Effective precision already includes both mask responsibilities and t4
    # robust scale weights; degrees_of_freedom=None prevents counting them twice.
    fit = fit_localization_fast(
        state, adapted, precision, lambda x: np.linalg.norm(x[:2]) <= 250.,
        max_iterations=64, deadline=start+25., degrees_of_freedom=None)
    inflated = []
    for port in adapted:
        if port.assignment < port.candidate_count:
            port.score_selected(fit.mean, port.assignment)
            inflated.extend(port.posterior_inflated.tolist())
    result = dict(
        unit=args.unit, arm=args.arm, parent_sha256=digest(path),
        source_freeze_sha256=digest(frozen), inputs=scan.inputs, height=height.input_bindings,
        observations=parent['observations'], assignments=assignments,
        probability=probability, extra_raw_scale_variance_hz2=1000.**2,
        mean=fit.mean.tolist(), objectives=list(fit.objectives), converged=fit.converged,
        reason=fit.reason, iterations=fit.iterations,
        position_change_m=float(1000*np.linalg.norm(fit.mean[:2]-state[:2])),
        original_objective=parent['best']['objectives'][-1],
        expected_inflated_samples=float(sum(inflated)),
        samples_with_posterior_above_half=sum(p > .5 for p in inflated),
        signal_sample_count=len(inflated), cpu_seconds=time.process_time()-cpu,
        seconds=time.monotonic()-start,
        qualification='Warm fixed-identity ablation. Bernoulli masks on raw samples add1000Hz '
        'scale before original offset-removing contrasts; each component retains original t4 '
        'shared scale and temporal covariance. Exact normalized finite mixture; original nonlinear '
        'means and nuisance priors unchanged. Control probability0 recovers baseline. Posterior '
        'mask probabilities are model-dependent, not verified bad samples. '
        'No GPS; not cold inference.')
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    args.output.with_suffix('.sha256').write_text(digest(args.output)+'\n')
    print(json.dumps({k: result[k] for k in ['unit', 'arm', 'converged', 'reason',
                                            'position_change_m', 'seconds']}))


if __name__ == '__main__':
    main()
