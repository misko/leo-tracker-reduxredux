"""Reference-blind training identity audit at sealed joint-fit endpoints."""
import json
import time
from pathlib import Path

import numpy as np
from candidate_joint_expansion_adapter import CandidateJointObjective
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent


def main():
    started = time.monotonic()
    directory = HERE/'candidate-joint-expansion-v1'
    freeze = directory/'sources.json'
    assert digest(freeze) == freeze.with_suffix('.sha256').read_text().strip()
    frozen = json.loads(freeze.read_text())
    verify_sources(frozen['source_sha256'])
    rows = []
    for unit, arm in frozen['pairs']:
        if arm != 'candidate':
            continue
        path = directory/(unit+'-'+arm+'.json')
        assert digest(path) == path.with_suffix('.sha256').read_text().strip()
        receipt = json.loads(path.read_text())
        assert receipt['converged']
        model = CandidateJointObjective(unit)
        assert receipt['parent_sha256'] == digest(model.base.parent_path)
        assert receipt['assignments'] == model.base.assignments
        verify_sources(receipt['inputs'])
        state = model.base.initial.copy()
        state[model.columns] = receipt['mean']
        changes = []
        for k, (port, assigned) in enumerate(zip(
                model.base.ports, model.base.assignments, strict=True)):
            scores = np.asarray(port.score_all(state))
            # Horizon-gated alternatives legitimately have negative infinity.
            assert not np.any(np.isnan(scores) | np.isposinf(scores))
            assert np.isfinite(scores[assigned])
            best = int(np.argmax(scores))
            if best != assigned:
                changes.append(dict(track_index=k, old_index=assigned, best_index=best,
                    old_is_clutter=assigned == port.candidate_count,
                    best_is_clutter=best == port.candidate_count,
                    training_score_gain=float(scores[best]-scores[assigned])))
        rows.append(dict(unit=unit, receipt_sha256=digest(path), changes=changes,
                         total_training_score_gain=sum(c['training_score_gain'] for c in changes)))
    result = dict(rows=rows, elapsed_s=time.monotonic()-started,
        freeze_sha256=digest(freeze), auditor_sha256=digest(__file__),
        qualification='No refit or GPS access. Training-factor preferred identities at the '
        'fixed joint endpoint only. Unassigned satellite epochs remain at parent values. '
        'A changed identity also changes candidate predictions and active epochs; training '
        'gains do not establish improvement of the complete joint objective or geography.')
    output = HERE/'candidate-joint-identity-stability-v1.json'
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
