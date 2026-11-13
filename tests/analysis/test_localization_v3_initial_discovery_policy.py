from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3 import initial_search as policy
from leo.analysis.localization_v3.region import SearchRegion


def prepared(monkeypatch):
    scan = SimpleNamespace(search_region=SearchRegion((10., 20.)), norads=np.arange(4))
    candidates = [dict(
        center_score=float(index),
        seed=dict(rows=[dict(component=str(index), candidate_index=index,
                             candidate_norad=100 + index)],
                  state=dict(beta=np.full(8, 999.), phases=np.array([20., -20., 7., 4.]),
                             smooth=np.ones((2, 1)), extra={})),
        aliases=[index],
    ) for index in range(4)]
    calls = SimpleNamespace(discovery=[], problems=[], fitted=[], mapped=[], notices=[])

    def discover(*args, **options):
        calls.discovery.append(options)
        return candidates

    def explore(*args, **kwargs):
        return candidates[0]['seed'], dict(candidate_hypotheses=1)

    def zero_state(scan):
        return dict(beta=np.zeros(8), phases=np.zeros(4), smooth=np.zeros((2, 1)), extra={})

    class Problem:
        def __init__(self, scan, node, sigma, fitted_c, *, reference):
            self.rows = node['seed']['rows']
            self.index = self.rows[0]['candidate_index']
            self.alias = node['aliases']
            self.reference = np.asarray(reference)
            self.node = node
            calls.problems.append(self)

        def residual(self, point):
            np.testing.assert_array_equal(point, np.zeros(2))
            score = 4 - self.index if self.reference.any() else self.index + 1
            return np.array([score], float)

        def state(self, point):
            return zero_state(scan)

        def calculate(self, point):
            return dict(conditional_residual_hz=np.zeros(4))

    def refreshed(scan, sigma, node, arm, **budgets):
        calls.fitted.append((node, arm, budgets))
        for name in ('beta', 'phases', 'smooth'):
            assert not node['seed']['state'][name].any()
        p = Problem(scan, node, sigma, arm == 'fitted_c', reference=np.zeros(1))
        score = p.index + 1 if arm == 'c0' else 4 - p.index
        result = dict(parameters=np.array([p.index / 10, -p.index / 10]), score=float(score))
        return p, result, [dict(epoch=i) for i in range(budgets['rounds'])]

    def mapper(operation, tasks):
        calls.mapped.append(tuple(tasks))
        return [operation(task) for task in tasks]

    monkeypatch.setattr(policy, 'fresh_discovery', discover)
    monkeypatch.setattr(policy, 'explore', explore)
    monkeypatch.setattr(policy, 'AnchoredFamilies', lambda *args: SimpleNamespace(alias=[0]))
    monkeypatch.setattr(policy, 'zero_state', zero_state)
    monkeypatch.setattr(policy, 'NormalPosition', Problem)
    monkeypatch.setattr(policy, 'refreshed', refreshed)
    monkeypatch.setattr(policy, 'actual_metrics', lambda *args: {})
    monkeypatch.setattr(policy, 'extend_associations', lambda *args: {})
    monkeypatch.setattr(policy, 'fit', lambda problem, **kwargs: dict(index=problem.index))
    return scan, candidates, calls, mapper


def test_warm_ranking_changes_only_selected_proposals_and_preserves_paired_full_fits(monkeypatch):
    scan, candidates, calls, mapper = prepared(monkeypatch)
    original = deepcopy(candidates)
    result = policy.initial_search(scan, 150., ranking_policy='warm-center-v1',
                                   map_branches=mapper, on_branch=calls.notices.append)
    assert calls.discovery == [dict(budget=4)]
    assert [c['node']['seed']['rows'][0]['candidate_index'] for c in result['choices']] == [3, 2, 1]
    assert result['fully_fitted_hypotheses'] == len(calls.notices) == 3
    assert calls.mapped == [tuple((i, arm) for i in range(3) for arm in ('c0', 'fitted_c'))]
    assert len(calls.fitted) == 6
    for first, second in zip(calls.fitted[::2], calls.fitted[1::2], strict=True):
        assert first[0] is second[0]
        assert (first[1], second[1]) == ('c0', 'fitted_c')
        assert first[2] == second[2] == dict(rounds=5, iterations=48)
    assert all(len(c['arms'][arm]['phase_rounds']) == 5
               for c in result['choices'] for arm in ('c0', 'fitted_c'))
    assert result['selected_hypothesis'] == 2
    assert result['zero_phase_control'] == dict(c0=dict(index=1), fitted_c=dict(index=1))
    assert result['initial_discovery_policy'] == dict(
        id='initial-discovery-v1', seed_policy='legacy', ranking_policy='warm-center-v1')
    ranking = result['initial_discovery_ranking']
    assert [r['cold_score'] for r in ranking] == [1., 4., 9., 16.]
    assert [r['ranking_score'] for r in ranking] == [16., 9., 4., 1.]
    warm = [p for p in calls.problems if p.reference.any()]
    assert len(warm) == 4
    assert [p.reference.item() for p in warm] == [15., -15., 7., 4.]
    for before, after in zip(original, candidates, strict=True):
        assert before['seed']['rows'] == after['seed']['rows']
        assert before['aliases'] == after['aliases']
        for name in ('beta', 'phases', 'smooth'):
            np.testing.assert_array_equal(before['seed']['state'][name],
                                          after['seed']['state'][name])


def test_default_and_explicit_legacy_keep_original_calls_fits_and_output(monkeypatch):
    from census_algo07v5_initial_controls import fingerprint

    scan, _, calls, _ = prepared(monkeypatch)
    default = policy.initial_search(scan, 150.)
    assert 'initial_discovery_policy' not in default
    assert 'initial_discovery_ranking' not in default
    selected = [c['node']['seed']['rows'][0]['candidate_index'] for c in default['choices']]
    assert selected == [0, 1, 2]
    assert len(calls.problems) == 12
    explicit = policy.initial_search(scan, 150., seed_policy='legacy', ranking_policy='legacy')
    assert calls.discovery == [dict(budget=4), dict(budget=4)]
    assert explicit.pop('initial_discovery_policy') == dict(
        id='initial-discovery-v1', seed_policy='legacy', ranking_policy='legacy')
    assert all(r['cold_score'] == r['ranking_score']
               for r in explicit.pop('initial_discovery_ranking'))
    assert fingerprint(default) == fingerprint(explicit)


def test_diverse_seed_policy_reaches_discovery_without_reducing_fit_budget(monkeypatch):
    scan, _, calls, _ = prepared(monkeypatch)
    result = policy.initial_search(scan, 150., seed_policy='anchor-round-robin-v1')
    assert calls.discovery == [dict(budget=4, seed_policy='anchor-round-robin-v1')]
    assert result['initial_discovery_policy']['ranking_policy'] == 'legacy'
    assert len(calls.fitted) == 6
    assert all(c[2] == dict(rounds=5, iterations=48) for c in calls.fitted)


@pytest.mark.parametrize('name', ['seed_policy', 'ranking_policy'])
@pytest.mark.parametrize('value', ['', 'unknown', True, 1])
def test_invalid_policy_fails_before_discovery(name, value, monkeypatch):
    monkeypatch.setattr(policy, 'fresh_discovery', lambda *args, **kwargs: pytest.fail(
        'Invalid policy must fail before reading scan evidence'))
    with pytest.raises(ValueError, match='initial .* policy'):
        policy.initial_search(None, 150., **{name: value})
