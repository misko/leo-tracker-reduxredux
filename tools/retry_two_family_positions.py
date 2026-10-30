"""Matched Powell controls/additions after a verified numerical-only failure."""
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
from fit_two_predictive_families import evidence
from phase_reference_checks import phase_refresh
from leo.analysis.research.joint_predictive_families import two_family_phase_evidence


def run(args):
    source = args.source
    # The whole matched experiment is selected on RF/numerical status, not GPS.
    failures = []
    for method in ('control', 'factorized', 'joint'):
        for arm in ('c0', 'fitted_c'):
            folder = source/(method+'-'+arm)
            a = read(folder/('audit-v2.json' if method == 'joint' else 'audit.json'))
            r = read(folder/'result.json')
            if a['incumbent_owner_changes'] or not all(v['all_pass'] for v in a['exact_incumbent_orbits']):
                raise ValueError('not a numerical-only experiment')
            if any(not value for key, value in a['checks'].items() if key != 'incumbent_and_numerical'):
                raise ValueError('physical/phase audit failure is not a numerical retry')
            if a['phase_check']['phase_change_s'] > .01:
                raise ValueError('phase refresh failure')
            failures.append(not r['history'][-1]['success'])
    if not any(failures):
        raise ValueError('no numerical failure to retry')
    prior = read(source/(args.method+'-'+args.arm)/'protocol.json')
    for path, digest in prior['source_hashes'].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest:
            raise ValueError('changed source: '+path)
    out = args.output
    out.mkdir(parents=True, exist_ok=False)
    inv = args.study/'all-large-track-recovery'/prior['job']['job_id']/'inventory.json'
    d = context(read(inv))
    families = [NewFamily(d['scan'], group, d['model'], phase_step=prior['phase_step_s'],
                          allow_uncalibrated_label=True) for group in prior['targets']]
    paths = [inv, Path(__file__), Path('tools/fit_two_predictive_families.py'),
             Path('tools/probe_joint_predictive_families.py'),
             Path('src/leo/analysis/research/joint_predictive_families.py')]
    paths += sorted(source.glob('*/result.json'))+sorted(source.glob('*/audit*.json'))
    hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    write(out/'protocol.json', dict(job=prior['job'], targets=prior['targets'], source_hashes=hashes,
          method=args.method, arm=args.arm, phase_step_s=prior['phase_step_s'],
          optimizer='Powell', maxiter=48, maxfev=240, phase_rounds=5,
          start_east_north_km=[0, 0], box_width_km=25, GPS_used=False, future_TLE=False,
          diagnostic_only=True, association_authorized=False, numerical_only_selection=True))
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
            penalty = float(np.sum(np.minimum(0, c['elevation'][p.keep])**2)/4)
            return c['negative_twice_elbo']+penalty+(0. if args.method == 'control' else evidence(families, p, z, d, args.method))
        opt = minimize(objective, x, method='Powell', bounds=[(-12.5, 12.5)]*2,
                       options=dict(maxiter=48, maxfev=240, ftol=1e-10, xtol=1e-5))
        x = np.asarray(opt.x)
        reference, check = phase_refresh(p.state(x)['phases'][p.labels], reference)
        row = dict(endpoint_east_north_km=x, objective=float(opt.fun), success=bool(opt.success),
                   message=str(opt.message), nfev=opt.nfev, **check)
        history.append(row)
        write(out/f'round-{iteration+1}.json', row)
        print(args.method, args.arm, iteration+1, opt.success, round(time.monotonic()-began, 1), flush=True)
    result = summary(p, x, d['entries'])
    result.update(history=history, method=args.method, arm=args.arm, optimizer='Powell',
                  incumbent_objective=result['negative_twice_elbo'])
    for method in ('joint', 'factorized'):
        result[method+'_evidence'] = evidence(families, p, x, d, method)
    if args.method != 'control':
        result['negative_twice_elbo'] += result[args.method+'_evidence']
    result.update(joint_phase_result=two_family_phase_evidence(*joint_inputs(families, p, x, d['powers'], d['entries'])),
                  joint_phase_grid_s=[f.phases for f in families], seconds=time.monotonic()-began,
                  association_authorized=False, pending_checks=['physical replay', 'ownership', 'phase resolution'])
    write(out/'result.json', result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('study', 'source', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--method', choices=['control', 'factorized', 'joint'], required=True)
    parser.add_argument('--arm', choices=['c0', 'fitted_c'], required=True)
    run(parser.parse_args())
