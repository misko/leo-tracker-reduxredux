"""One bounded alternating association/continuous search from sealed joint parents."""
import argparse
import json
import resource
import sys
import time
from pathlib import Path

import numpy as np
from candidate_calibrated_cached_joint import CandidateJointObjective
from calibrated_proposal_delta import ProposalDelta
from candidate_calibrated_joint import CandidateJointObjective as Original
from diagnose_candidate_reassociation import training_information
from regression_batch import digest, verify_sources

from leo.analysis.localization_epoch_profile import profile_unused_epochs
from leo.analysis.localization_joint_search import fit_joint_objective

HERE = Path(__file__).resolve().parent


def main():
    start = time.monotonic()
    deadline = start+25.
    parser = argparse.ArgumentParser()
    parser.add_argument('unit')
    parser.add_argument('--arm', choices=['control', 'candidate'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    parent_path = HERE/'calibrated-joint-v1'/(args.unit+'-candidate.json')
    if not parent_path.exists():
        parent_path = HERE/'calibrated-joint-expansion-v1'/(args.unit+'-candidate.json')
    assert digest(parent_path) == parent_path.with_suffix('.sha256').read_text().strip()
    parent = json.loads(parent_path.read_text())
    original = Original(args.unit)
    verify_sources(original.base.parent['source_sha256'])
    verify_sources(original.base.parent['inputs'])
    state = original.base.initial.copy()
    state[original.columns] = parent['mean']
    initial = state.copy()
    assignments = parent['assignments'].copy()
    history, trials, fits, profiles = [], [], [], []
    converged, reason = False, 'round_limit'
    count = len(state)-5

    def check_time():
        if time.monotonic() >= deadline:
            raise TimeoutError('single total diagnostic deadline')

    def build(full, choices):
        check_time()
        return CandidateJointObjective(args.unit, state=full, assignments=choices,
                                       context=original.base)

    def profiled(full, choices):
        before = build(full, choices)
        training, candidate = before.base.components(before.initial[:2])
        old_value = training-candidate
        clean, gain = profile_unused_epochs(full, choices, count)
        after = build(clean, choices) if gain else before
        training, candidate = after.base.components(after.initial[:2])
        value = training-candidate
        # Background visibility can depend on all epochs: check independence.
        discrepancy = old_value-value-gain
        assert abs(discrepancy) < 1e-7, 'unused epoch changes observation likelihood'
        profiles.append(dict(prior_gain=gain, discrepancy=discrepancy))
        return clean, after, value

    model, metric, value = None, None, None
    try:
        state, model, value = profiled(state, assignments)
        history.extend([parent['final_objective'], value])
        for iteration in range(12):
            check_time()
            metric = training_information(model)
            lower = min(t.times_s.min() for _, t in model.base.scan.tracks)
            upper = max(t.times_s.max() for _, t in model.base.scan.tracks)

            def support(x, model=model, lower=lower, upper=upper):
                full = model.base.initial.copy()
                full[model.columns] = x
                shifts = full[2]+full[5:]
                bank = model.base.scan.bank
                return (np.all(np.isfinite(x)) and np.linalg.norm(x[:2]) <= 250
                        and np.all(lower+shifts >= bank.times_s[1]+1e-4)
                        and np.all(upper+shifts <= bank.times_s[-2]-1e-4))

            fit = fit_joint_objective(state[model.columns], model.evaluate, metric,
                                     support, deadline=deadline, max_iterations=64)
            state[model.columns] = fit.mean
            value = model.evaluate(fit.mean, gradient=False)[0]
            fits.append(dict(converged=fit.converged, reason=fit.reason,
                             iterations=fit.iterations, objectives=list(fit.objectives)))
            history.append(value)
            if not fit.converged:
                reason = fit.reason
                break
            if args.arm == 'control':
                converged, reason = True, 'control_stationary'
                break
            proposals = []
            for k, (port, old) in enumerate(zip(model.base.ports, assignments, strict=True)):
                check_time()
                scores = np.asarray(port.score_all(state)).copy()
                incumbent = float(scores[old])
                scores[old] = -np.inf
                best = int(np.argmax(scores))
                if np.isfinite(scores[best]):
                    proposals.append((float(scores[best]-incumbent), k, best))
            proposals.sort(key=lambda p: (-p[0], p[1], p[2]))
            scorer = ProposalDelta(build(state, assignments))
            assert abs(scorer.value-value) < 1e-7
            best_trial = None
            for _, track, identity in proposals:
                check_time()
                candidate_value, clean, choices, _ = scorer.score(track, identity)
                trials.append(dict(iteration=iteration, track=track, identity=identity,
                                   before=value, after=candidate_value))
                if candidate_value < value-1e-7 and (
                        best_trial is None or candidate_value < best_trial[0]):
                    best_trial = (candidate_value, clean, choices)
            if best_trial is None:
                converged = True
                reason = 'no_improving_best_alternative'
                break
            if iteration == 11:
                reason = 'round_limit'
                break
            value, state, assignments = best_trial
            model = build(state, assignments)
            history.append(value)
    except TimeoutError:
        reason = 'wall_budget'
    result = dict(unit=args.unit, arm=args.arm, converged=converged, reason=reason,
        parent_sha256=digest(parent_path), inputs=original.base.parent['inputs'],
        height=parent['height'], initial_full_state=initial.tolist(),
        full_state=state.tolist(), assignments=assignments, history=history,
        profiles=profiles, trials=trials, fits=fits, final_objective=value,
        metric=metric.tolist() if metric is not None else None,
        columns=model.columns.tolist() if model is not None else None,
        metric_state=model.base.initial.tolist() if model is not None else None,
        seconds=time.monotonic()-start, sources={},
        qualification='Warm alternating diagnostic, max12continuous fits and one best-training '
        'alternative per track per round under one25s deadline. Exact unused-epoch profiling '
        'with likelihood-independence check. No global discrete optimum, GPS, cold90s '
        'or calibration claim. Limit exits remain failures.')
    for module in tuple(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if filename:
            path = Path(filename).resolve()
            if path.suffix == '.py' and path.is_relative_to(HERE.parents[1]):
                result['sources'][str(path)] = digest(path)
    usage = resource.getrusage(resource.RUSAGE_SELF)
    result['cpu_s'] = usage.ru_utime+usage.ru_stime
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    args.output.with_suffix('.sha256').write_text(digest(args.output)+'\n')
    print(json.dumps(dict(unit=args.unit, arm=args.arm, reason=reason,
                         seconds=result['seconds'])))


if __name__ == '__main__':
    main()
