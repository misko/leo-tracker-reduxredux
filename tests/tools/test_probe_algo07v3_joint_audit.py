import hashlib
import json

import numpy as np
import pytest
from probe_algo07v3_joint_audit import measure_trials, qualified_inputs

from leo.analysis.localization_v3 import joint_recovery as joint
from leo.analysis.localization_v3.numerical_policy import NumericalPolicy
from leo.operations.localization_v3_parallel import ParallelFitFailure, map_grid_batches


def test_fresh_checkpoint_trials_keep_order_and_full_grid(monkeypatch):
    monkeypatch.setattr(joint, 'evidence', lambda f, p, x, d, m: float(x.sum() + f))
    policy = NumericalPolicy()
    args = ([1, 2, 3], object(), np.array([0., 0.]), {'numerical_policy': policy},
            'joint', np.array([[0., 0.], [.025, 0.], [-.025, 0.], [0., .025], [0., -.025]]))
    rows = measure_trials(joint._quadrature_scores, args, map_grid_batches, lambda row: None)
    assert [r['side'] for r in rows] == ['baseline', 'candidate', 'candidate', 'baseline']
    assert all(r['exact'] and np.array(r['scores']).shape == (5, 3) for r in rows)
    assert len({r['score_signature'] for r in rows}) == 1
    assert policy.receipt['problem_count'] == 0


def test_grid_difference_fails_even_if_scalar_mean_is_equal():
    def differing(f, p, x, d, m, offsets, mapper):
        return np.array([[1., 2.]]) if mapper is None else np.array([[2., 1.]])
    rows = []
    with pytest.raises(ValueError, match='grid differs'):
        measure_trials(differing, (None, None, None, {}, None, None), object(), rows.append)
    assert len(rows) == 2 and not rows[-1]['exact']


def test_receipt_mutation_aborts_without_mutating_original_parent():
    policy = NumericalPolicy()
    def mutate(f, p, x, d, m, offsets, mapper):
        d['numerical_policy'].receipt['problem_count'] += 1
        return np.ones((5, 3))
    with pytest.raises(ParallelFitFailure, match='changed numerical receipts'):
        measure_trials(mutate, (None, None, None, {'numerical_policy': policy}, None, None),
                       object(), lambda row: None)
    assert policy.receipt['problem_count'] == 0


@pytest.mark.parametrize('fault', [None, 'different', 'changed', 'missing_arm'])
def test_native_qualification_binds_the_actual_request(tmp_path, fault):
    request = dict(identity='native-scan', output_root='fresh')
    bindings = {}
    for side in ('baseline', 'candidate'):
        path = tmp_path / f'{side}-request.json'
        path.write_text(json.dumps(dict(request, output_root=side)))
        bindings[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    comparison = tmp_path / 'comparison.json'
    comparison.write_text(json.dumps(dict(exact_owned_science_and_artifacts=True,
        both_c_arms=fault != 'missing_arm', input_bindings=bindings)))
    if fault == 'different':
        request['identity'] = 'another-scan'
    if fault == 'changed':
        path.write_text('{}')
    if fault is None:
        assert len(qualified_inputs(comparison, request)) == 2
    else:
        with pytest.raises(ValueError):
            qualified_inputs(comparison, request)
