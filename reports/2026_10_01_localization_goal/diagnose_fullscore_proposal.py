"""Bounded warm joint fit with fixed identities and verified candidate gradients."""
import argparse
import json
import resource
import sys
import time
from pathlib import Path

import numpy as np
from candidate_reassociation_joint import CandidateJointObjective
from regression_batch import digest, verify_sources

from leo.analysis.localization_epoch_profile import profile_unused_epochs
from leo.analysis.localization_joint_search import fit_joint_objective

HERE = Path(__file__).resolve().parent


def training_information(model):
    b = model.base
    precision = np.r_[0., 0., 1., np.full(b.initial.size-3, 4.)]
    information = np.diag(precision[model.columns])
    for p, index in zip(b.ports, b.assignments, strict=True):
        if index == p.candidate_count:
            continue
        prediction = p.predict_selected(b.initial, index)
        residual = p.observation-prediction.mean
        solved = np.linalg.solve(prediction.covariance, residual)
        weight = (4+len(residual))/(4+float(residual@solved))
        j = prediction.jacobian[:, model.columns]
        information += weight*j.T@np.linalg.solve(prediction.covariance, j)
    return (information+information.T)*.5


def main():
    start = time.monotonic()
    parser = argparse.ArgumentParser()
    parser.add_argument('unit')
    parser.add_argument('--arm', choices=['control', 'candidate'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    audit_path = HERE/'proposal-coverage-v1'/(args.unit+'.json')
    assert digest(audit_path) == audit_path.with_suffix('.sha256').read_text().strip()
    audit = json.loads(audit_path.read_text())
    assert audit['complete']
    proposal = audit['best']
    assert proposal['full_objective_gain'] > 0
    parent_path = HERE/'alternating-expansion-v1'/(args.unit+'-candidate.json')
    assert digest(parent_path) == parent_path.with_suffix('.sha256').read_text().strip()
    parent = json.loads(parent_path.read_text())
    state = np.asarray(parent['full_state'])
    assignments = parent['assignments'].copy()
    if args.arm == 'candidate':
        assignments[proposal['track']] = proposal['new_identity']
    state, prior_gain = profile_unused_epochs(state, assignments, len(state)-5)
    model = CandidateJointObjective(args.unit, state=state, assignments=assignments)
    b = model.base
    verify_sources(b.parent['source_sha256'])
    verify_sources(b.parent['inputs'])
    information = training_information(model)
    lower = min(t.times_s.min() for _, t in b.scan.tracks)
    upper = max(t.times_s.max() for _, t in b.scan.tracks)

    def support(x):
        state = b.initial.copy()
        state[model.columns] = x
        shifts = state[2]+state[5:]
        return (np.linalg.norm(x[:2]) <= 250. and np.all(np.isfinite(x))
                and np.all(lower+shifts >= b.scan.bank.times_s[1]+1e-4)
                and np.all(upper+shifts <= b.scan.bank.times_s[-2]-1e-4))

    weight = 1.
    fit = fit_joint_objective(model.initial,
        lambda x: model.evaluate(x, candidate_weight=weight), information, support,
        deadline=start+25., max_iterations=64)
    value, gradient = model.evaluate(fit.mean, candidate_weight=weight)
    decrement = float(gradient@np.linalg.solve(information, gradient))
    result = dict(unit=args.unit, arm=args.arm, parent_sha256=digest(b.parent_path),
                  inputs=b.parent['inputs'], height=b.parent['height'],
                  assignments=b.assignments, columns=model.columns.tolist(),
                  initial=model.initial.tolist(), mean=fit.mean.tolist(),
                  information=information.tolist(), objectives=list(fit.objectives),
                  final_objective=value, final_decrement_squared=decrement,
                  converged=fit.converged, reason=fit.reason, iterations=fit.iterations,
                  position_change_m=float(np.linalg.norm(fit.mean[:2]-model.initial[:2])*1000),
                  sources={}, inherited_full_state=state.tolist(),
                  joint_parent_sha256=digest(parent_path), proposal=proposal,
                  parent_joint_objective=parent['final_objective'],
                  reassociation_audit_sha256=digest(audit_path), profiled_prior_gain=prior_gain)
    for module in tuple(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if filename:
            p = Path(filename).resolve()
            if p.suffix == '.py' and p.is_relative_to(HERE.parents[1]):
                result['sources'][str(p)] = digest(p)
    usage = resource.getrusage(resource.RUSAGE_SELF)
    result.update(seconds=time.monotonic()-start, cpu_s=usage.ru_utime+usage.ru_stime,
        qualification='One full-objective-selected identity swap, then warm fitting. '
        'Best complete-objective alternative despite training-score loss; unused epochs '
        'profiled to zero. Not a complete discrete search. Original '
        'Gaussian shared clock/drift/epoch priors, uniform250km Sacramento support and100ftMSL '
        'height. Former checking candidates are now training data. Training IRLS information '
        'is optimizer metric only, not posterior covariance. No GPS or independent validation.')
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    args.output.with_suffix('.sha256').write_text(digest(args.output)+'\n')
    print(json.dumps(dict(unit=args.unit, arm=args.arm, converged=fit.converged,
                          reason=fit.reason, seconds=result['seconds'])))


if __name__ == '__main__':
    main()
