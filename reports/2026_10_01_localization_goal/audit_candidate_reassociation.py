"""Check exact full-objective reassociation changes before fitting any proposals."""
import json
import time
from pathlib import Path

import numpy as np
from candidate_joint_expansion_adapter import CandidateJointObjective as Original
from candidate_reassociation_joint import CandidateJointObjective
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent


def main():
    started = time.monotonic()
    source = HERE/'candidate-joint-identity-stability-v1.json'
    assert digest(source) == source.with_suffix('.sha256').read_text().strip()
    stability = json.loads(source.read_text())
    directory = HERE/'candidate-joint-expansion-v1'
    freeze = directory/'sources.json'
    assert digest(freeze) == stability['freeze_sha256']
    bound = json.loads(freeze.read_text())['source_sha256']
    for name in ['audit_candidate_reassociation.py', 'candidate_reassociation_joint.py',
                 'candidate_reassociation_spatial.py']:
        path = HERE/name
        bound[str(path)] = digest(path)
    verify_sources(bound)
    rows = []
    for entry in stability['rows']:
        unit = entry['unit']
        receipt_path = directory/(unit+'-candidate.json')
        assert digest(receipt_path) == entry['receipt_sha256']
        receipt = json.loads(receipt_path.read_text())
        original = Original(unit)
        state = original.base.initial.copy()
        state[original.columns] = receipt['mean']
        value, gradient = original.evaluate(np.asarray(receipt['mean']))
        assert abs(value-receipt['final_objective']) < 1e-7
        rebuilt = CandidateJointObjective(unit, state=state, assignments=receipt['assignments'])
        same_value, same_gradient = rebuilt.evaluate(rebuilt.initial)
        assert np.array_equal(original.columns, rebuilt.columns)
        assert abs(same_value-value) < 1e-7
        assert np.max(np.abs(same_gradient-gradient)) < 1e-7
        train, candidate = rebuilt.base.components(state[:2])
        assert abs(train-candidate-value) < 1e-7
        proposals = []
        for change in entry['changes']:
            assignments = receipt['assignments'].copy()
            assignments[change['track_index']] = change['best_index']
            model = CandidateJointObjective(unit, state=state, assignments=assignments)
            new_value, new_gradient = model.evaluate(model.initial)
            new_train, new_candidate = model.base.components(state[:2])
            assert abs(new_train-new_candidate-new_value) < 1e-7
            assert abs((train-new_train)-change['training_score_gain']) < 1e-7
            # Independent directional differences exercise all new active coordinates.
            rng = np.random.default_rng(20261001)
            discrepancies = []
            for _ in range(3):
                direction = rng.normal(size=len(model.initial))
                direction /= np.linalg.norm(direction)
                h = .0005
                plus = model.evaluate(model.initial+h*direction, gradient=False)[0]
                minus = model.evaluate(model.initial-h*direction, gradient=False)[0]
                discrepancies.append(abs((plus-minus)/(2*h)-new_gradient@direction))
            assert max(discrepancies) < .005
            proposals.append(dict(**change, joint_objective_gain=value-new_value,
                candidate_log_ratio_gain=new_candidate-candidate,
                maximum_directional_gradient_discrepancy=max(discrepancies),
                proposed_active_dimensions=len(model.columns),
                original_active_dimensions=len(original.columns)))
        rows.append(dict(unit=unit, identical_assignment_value_difference=same_value-value,
                         proposals=proposals))
    verify_sources(bound)
    result = dict(rows=rows, elapsed_s=time.monotonic()-started,
        source_sha256=bound, identity_audit_sha256=digest(source),
        qualification='No GPS, fitting or identity acceptance. Exact fixed-state changes '
        'in complete joint objective with rebuilt candidate graph and active epochs. '
        'Three directional derivative checks per proposal; not full coordinate audit. '
        'Epochs no longer used remain fixed at inherited values, preserving prior value. '
        'Future optimization must account explicitly for unused epoch priors.')
    output = HERE/'candidate-reassociation-audit-v1.json'
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'source_sha256'}, indent=2))


if __name__ == '__main__':
    main()
