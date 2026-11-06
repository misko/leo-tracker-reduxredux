from types import SimpleNamespace

import algo07v3_preinitialqueue_oracle as policy
import numpy as np
import pytest
from probe_algo07v3_initial_queue import transform

from leo.analysis.localization_v3.region import SearchRegion


@pytest.mark.parametrize('branches', [1, 2, 3])
def test_queue_keeps_cold_inputs_common_winner_and_ordered_callbacks(monkeypatch, branches):
    scan = SimpleNamespace(search_region=SearchRegion((10., 20.)), norads=np.arange(3))
    candidates = [dict(center_score=float(i), seed=dict(rows=[dict(component=str(i),
        candidate_index=i, candidate_norad=100+i)], state={'beta': np.ones(8)*999}),
        aliases=[0]) for i in range(3)]
    monkeypatch.setattr(policy, 'fresh_discovery', lambda *a, **k: candidates)
    corners, paired, notices = [], [], []

    def explore(scan, state, point, method, **kwargs):
        corners.append(point)
        assert state is candidates[0]['seed']['state']
        assert kwargs == dict(compact_update=False)
        return candidates[0]['seed'], dict(candidate_hypotheses=[])

    monkeypatch.setattr(policy, 'explore', explore)
    monkeypatch.setattr(policy, 'AnchoredFamilies', lambda *a: SimpleNamespace(alias=[0]))
    monkeypatch.setattr(policy, 'zero_state', lambda scan: dict(beta=np.zeros(8)))

    class Problem:
        def __init__(self, scan, node, sigma, fitted, reference):
            assert not node['seed']['state']['beta'].any()
            self.rows = node['seed']['rows']
            self.index = self.rows[0]['candidate_index']
            self.alias, self.reference = node['aliases'], reference
        def residual(self, x):
            return np.array([3-self.index], float)
        def state(self, x):
            return dict(beta=np.zeros(8))
        def calculate(self, x):
            return dict(conditional_residual_hz=np.zeros(4))

    def refresh(scan, sigma, node, arm, **budgets):
        paired.append((node, arm, budgets))
        p = Problem(scan, node, sigma, arm == 'fitted_c', np.zeros(1))
        # c0 prefers index 1, fitted-c prefers index 0. Select one common branch.
        score = [3., 1., 2.][p.index] if arm == 'c0' else [1., 2., 3.][p.index]
        return p, dict(parameters=np.zeros(2), score=score), []

    monkeypatch.setattr(policy, 'NormalPosition', Problem)
    monkeypatch.setattr(policy, 'refreshed', refresh)
    monkeypatch.setattr(policy, 'actual_metrics', lambda *a: {})
    monkeypatch.setattr(policy, 'extend_associations', lambda *a: {})
    monkeypatch.setattr(policy, 'fit', lambda p, **kw: dict(index=p.index))
    mapped = []
    def mapper(operation, arms):
        mapped.append(tuple(arms))
        return [operation(arm) for arm in arms]
    operation, _, _ = transform(mapper)
    result = operation(scan, 150., on_branch=notices.append, branch_budget=branches)
    assert mapped == [tuple((i, a) for i in range(branches) for a in ('c0', 'fitted_c'))]
    assert corners == [(-12.5, -12.5), (-12.5, 12.5), (12.5, -12.5), (12.5, 12.5)]
    assert result['unique_RF_hypotheses'] == 3  # Corner aliases deduplicate.
    assert len(notices) == result['fully_fitted_hypotheses'] == branches
    assert [c['node']['seed']['rows'][0]['candidate_index'] for c in notices] == (
        [2, 1, 0][:branches])
    selected = 2 if branches == 1 else 1
    assert result['selected_hypothesis'] == (0 if branches == 1 else 1)
    assert result['zero_phase_control'] == dict(c0=dict(index=selected),
                                               fitted_c=dict(index=selected))
    for first, second in zip(paired[::2], paired[1::2], strict=True):
        assert first[0] is second[0]
        assert (first[1], second[1]) == ('c0', 'fitted_c')
        assert first[2] == second[2] == dict(rounds=5, iterations=48)
    assert candidates[0]['seed']['state']['beta'][0] == 999


@pytest.mark.parametrize('queued', [False, True])
def test_real_bounded_search_matches_full_result_and_callbacks(queued):
    from check_algo07v3_scan_likelihood import fingerprint

    from leo.operations.localization_v3_parallel import map_annotation_training, map_initial_arms
    from tests.analysis.test_localization_v3_position import prepared

    first, _ = prepared()
    second, _ = prepared()
    notices = []
    budgets = dict(seed_budget=1, branch_budget=3, rounds=1, iterations=2)
    expected = policy.initial_search(first, 150., map_arms=map_initial_arms, **budgets)
    operation, _, _ = transform(map_annotation_training if queued else map)
    actual = operation(second, 150., on_branch=notices.append, **budgets)
    assert fingerprint(actual) == fingerprint(expected)
    assert fingerprint(notices) == fingerprint(expected['choices'])


@pytest.mark.parametrize('extra', [-1, 1])
def test_missing_or_extra_worker_result_is_not_accepted(extra):
    from tests.analysis.test_localization_v3_position import prepared
    scan, _ = prepared()

    def mapper(operation, tasks):
        return [None] * (len(tasks) + extra)

    operation, _, _ = transform(mapper)
    with pytest.raises(ValueError, match='One result per initial branch/arm'):
        operation(scan, 150., seed_budget=1, branch_budget=1, rounds=1, iterations=1)


def test_worker_failure_propagates_without_a_selected_result():
    from tests.analysis.test_localization_v3_position import prepared
    scan, _ = prepared()

    def mapper(operation, tasks):
        raise RuntimeError('deliberate worker failure')

    operation, _, _ = transform(mapper)
    with pytest.raises(RuntimeError, match='deliberate worker failure'):
        operation(scan, 150., seed_budget=1, branch_budget=1, rounds=1, iterations=1)
