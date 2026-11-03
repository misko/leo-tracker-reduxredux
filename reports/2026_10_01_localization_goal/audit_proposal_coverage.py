"""Bounded full-objective scoring of training-disfavored single-track alternatives."""
import argparse
import json
import resource
import time
from pathlib import Path

import numpy as np
from candidate_cached_joint import CandidateJointObjective
from candidate_joint_expansion_adapter import CandidateJointObjective as Original
from regression_batch import digest, verify_sources

from leo.analysis.localization_epoch_profile import profile_unused_epochs

HERE = Path(__file__).resolve().parent


def main():
    started = time.monotonic()
    parser = argparse.ArgumentParser()
    parser.add_argument('unit')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    freeze = args.output.parent/'sources.json'
    assert digest(freeze) == freeze.with_suffix('.sha256').read_text().strip()
    sources = json.loads(freeze.read_text())['source_sha256']
    verify_sources(sources)
    path = HERE/'alternating-expansion-v1'/(args.unit+'-candidate.json')
    assert digest(path) == path.with_suffix('.sha256').read_text().strip()
    receipt = json.loads(path.read_text())
    assert receipt['converged'] and not receipt['trials']
    original = Original(args.unit)
    verify_sources(original.base.parent['inputs'])
    state = np.asarray(receipt['full_state'])
    assignments = receipt['assignments']
    model = CandidateJointObjective(args.unit, state=state, assignments=assignments,
                                    context=original.base)
    value = model.evaluate(model.initial, gradient=False)[0]
    assert abs(value-receipt['final_objective']) < 1e-7
    rows, complete = [], True
    for track, (port, old) in enumerate(zip(model.base.ports, assignments, strict=True)):
        if time.monotonic()-started >= 25:
            complete = False
            break
        scores = np.asarray(port.score_all(state)).copy()
        incumbent = float(scores[old])
        assert np.isfinite(incumbent)
        scores[old] = -np.inf
        new = int(np.argmax(scores))
        if not np.isfinite(scores[new]):
            continue
        choices = list(assignments)
        choices[track] = new
        proposal = CandidateJointObjective(args.unit, state=state, assignments=choices,
                                           context=original.base)
        raw_value = proposal.evaluate(proposal.initial, gradient=False)[0]
        clean, prior_gain = profile_unused_epochs(state, choices, len(state)-5)
        if prior_gain:
            proposal = CandidateJointObjective(args.unit, state=clean, assignments=choices,
                                               context=original.base)
        proposed_value = proposal.evaluate(proposal.initial, gradient=False)[0]
        assert abs(raw_value-proposed_value-prior_gain) < 1e-7
        train, candidate = proposal.base.components(clean[:2])
        assert abs(train-candidate-proposed_value) < 1e-7
        rows.append(dict(track=track, old_identity=old, new_identity=new,
            training_gain=float(scores[new]-incumbent), profiled_prior_gain=prior_gain,
            full_objective_gain=value-proposed_value,
            old_is_clutter=old == port.candidate_count,
            new_is_clutter=new == port.candidate_count))
    verify_sources(sources)
    usage = resource.getrusage(resource.RUSAGE_SELF)
    result = dict(unit=args.unit, complete=complete, track_count=len(model.base.ports),
        evaluated_alternatives=len(rows), rows=rows,
        full_objective_improvements=sum(r['full_objective_gain'] > 1e-7 for r in rows),
        best=max(rows, key=lambda r: r['full_objective_gain']) if rows else None,
        seconds=time.monotonic()-started, cpu_s=usage.ru_utime+usage.ru_stime,
        parent_sha256=digest(path), freeze_sha256=digest(freeze),
        qualification='No GPS, fitting, or identity acceptance. One best-training alternative '
        'per track even if worse than incumbent. Exact full-objective scoring and unused '
        'epoch profiling, scalar spatial parity. Not an exhaustive catalogue search. '
        'Incomplete deadline-limited scans retained as incomplete.')
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    args.output.with_suffix('.sha256').write_text(digest(args.output)+'\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}, indent=2))


if __name__ == '__main__':
    main()
