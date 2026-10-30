"""Bounded diagnostic position fit of two independently annotated new families.

This experiment does not authorize association or publish a position. Joint
physical/ownership replay and phase-resolution validation remain separate.
"""
import argparse
import hashlib
import time
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

from debug_fast_graph_unassociated import read, write
from diagnose_all_large_tracks import context
from ds23_frequency_events import make_event_problem, attach_event_predictive
from probe_ds23_frequency_events import cached, summary
from predictive_new_family import NewFamily
from probe_joint_predictive_families import joint_inputs
from phase_reference_checks import phase_refresh
from leo.analysis.research.joint_predictive_families import two_family_phase_evidence
from leo.analysis.research.predictive_track import phase_mixture_evidence


def evidence(families, p, x, d, method):
    inputs = joint_inputs(families, p, x, d['powers'], d['entries'])
    if method == 'joint':
        return two_family_phase_evidence(*inputs)['negative_twice_log_density']
    y, means, covariance, modes, priors, visible = inputs
    n = len(y[0])
    return sum(phase_mixture_evidence(y[k], means[k], covariance[sl, sl],
                                     modes[k], priors[k], visible[k])['negative_twice_log_density']
               for k, sl in enumerate((slice(0, n), slice(n, len(covariance)))))


def run(args):
    out = args.output
    out.mkdir(parents=True, exist_ok=False)
    probe = read(args.probe / 'protocol.json')
    receipt = read(args.probe / 'result.json')
    if not (receipt['all_individual_replays_verified'] and receipt['receiver_calibration_unchanged']):
        raise ValueError('verified joint input probe required')
    for path, digest in probe['source_hashes'].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest:
            raise ValueError('probe source changed: ' + path)
    inventory = args.study / 'all-large-track-recovery' / probe['job']['job_id'] / 'inventory.json'
    d = context(read(inventory))
    families = [NewFamily(d['scan'], group, d['model'], phase_step=args.phase_step,
                          allow_uncalibrated_label=True) for group in probe['targets']]
    sources = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
               for p in (args.probe / 'protocol.json', args.probe / 'result.json', inventory,
                         Path(__file__), Path('tools/probe_joint_predictive_families.py'),
                         Path('src/leo/analysis/research/joint_predictive_families.py'))}
    write(out / 'protocol.json', dict(job=probe['job'], targets=probe['targets'],
          source_hashes=sources, method=args.method, arm=args.arm, phase_step_s=args.phase_step,
          start_east_north_km=[0, 0], box_width_km=25, phase_rounds=5,
          maxiter=48, maxfun=240, GPS_used=False, future_TLE=False,
          diagnostic_only=True, association_authorized=False))
    began = time.monotonic()
    x = np.zeros(2)
    reference = np.zeros(len(d['means']))
    history = []
    for iteration in range(5):
        kw = {'base_problem_factory': d['problem_factory']} if 'problem_factory' in d else {}
        p = make_event_problem(d['scan'], d['node'], d['keep'], args.arm, reference,
                               d['powers'], d['means'], d['model'], [], **kw)
        attach_event_predictive(p, d['entries'], d['powers'])
        cached(p)

        def objective(z):
            c = p.calculate(z)
            penalty = float(np.sum(np.minimum(0, c['elevation'][p.keep]) ** 2) / 4)
            addition = 0. if args.method == 'control' else evidence(families, p, z, d, args.method)
            return c['negative_twice_elbo'] + penalty + addition

        opt = minimize(objective, x, method='L-BFGS-B', bounds=[(-12.5, 12.5)] * 2,
                       options=dict(maxiter=48, maxfun=240, eps=.001, ftol=1e-10,
                                    gtol=1e-4, maxls=20))
        x = np.asarray(opt.x)
        reference, check = phase_refresh(p.state(x)['phases'][p.labels], reference)
        row = dict(endpoint_east_north_km=x, objective=float(opt.fun),
                   success=bool(opt.success), message=str(opt.message), nfev=opt.nfev, **check)
        history.append(row)
        write(out / f'round-{iteration+1}.json', row)
        print(args.method, args.arm, iteration+1, x.tolist(), opt.success,
              round(time.monotonic()-began, 1), flush=True)
    result = summary(p, x, d['entries'])
    result['history'] = history
    result['method'] = args.method
    result['arm'] = args.arm
    result['incumbent_objective'] = result['negative_twice_elbo']
    # Both likelihoods are evaluated at every endpoint for a matched comparison.
    result['joint_evidence'] = evidence(families, p, x, d, 'joint')
    result['factorized_evidence'] = evidence(families, p, x, d, 'factorized')
    if args.method != 'control':
        result['negative_twice_elbo'] += result[args.method + '_evidence']
    result['joint_phase_result'] = two_family_phase_evidence(
        *joint_inputs(families, p, x, d['powers'], d['entries']))
    result['joint_phase_grid_s'] = [f.phases for f in families]
    result['seconds'] = time.monotonic()-began
    result['association_authorized'] = False
    result['pending_checks'] = ['joint target physical residuals', 'exact incumbent orbit replay',
                                'membership and ownership', 'local phase quadrature agreement']
    write(out / 'result.json', result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('study', 'probe', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--method', choices=['control', 'factorized', 'joint'], required=True)
    parser.add_argument('--arm', choices=['c0', 'fitted_c'], required=True)
    parser.add_argument('--phase-step', type=float, default=.0625)
    run(parser.parse_args())
