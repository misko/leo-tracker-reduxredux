from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3 import initial_search as policy
from leo.analysis.localization_v3.region import SearchRegion


def test_branch_ranking_cold_start_and_common_c0_winner(monkeypatch):
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
    result = policy.initial_search(scan, 150., on_branch=notices.append)
    assert corners == [(-12.5, -12.5), (-12.5, 12.5), (12.5, -12.5), (12.5, 12.5)]
    assert result['unique_RF_hypotheses'] == 3  # Corner aliases deduplicate.
    assert len(notices) == result['fully_fitted_hypotheses'] == 3
    assert [c['node']['seed']['rows'][0]['candidate_index'] for c in notices] == [2, 1, 0]
    assert result['selected_hypothesis'] == 1
    assert result['zero_phase_control'] == dict(c0=dict(index=1), fitted_c=dict(index=1))
    for first, second in zip(paired[::2], paired[1::2], strict=True):
        assert first[0] is second[0]
        assert (first[1], second[1]) == ('c0', 'fitted_c')
        assert first[2] == second[2] == dict(rounds=5, iterations=48)
    assert candidates[0]['seed']['state']['beta'][0] == 999


@pytest.mark.parametrize('bad', [0, -1, True, 1.5])
def test_invalid_budgets_fail_before_any_search(bad):
    with pytest.raises(ValueError, match='integer'):
        policy.initial_search(None, 150., rounds=bad)
