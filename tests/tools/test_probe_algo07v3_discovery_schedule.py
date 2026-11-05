import ast

import probe_algo07v3_discovery_schedule as probe
import pytest
from check_algo07v3_scan_likelihood import fingerprint

from tests.analysis.test_localization_v3_position import prepared


def test_extraction_preserves_each_seed_body_and_return_expression():
    _, source, candidate = probe.transform()
    old = ast.parse(source).body[0].body[-2]
    new = ast.parse(candidate).body[0].body[-2]
    assert [ast.dump(n) for n in old.body[:-1]] == [ast.dump(n) for n in new.body[1:-1]]
    assert ast.dump(old.body[-1].value.args[0]) == ast.dump(new.body[-1].value)


@pytest.mark.parametrize('budget', [1, 4])
@pytest.mark.parametrize('parallel', [False, True])
def test_complete_discovery_matches_with_unchanged_seed_order(budget, parallel):
    baseline, _ = prepared()
    candidate, _ = prepared()
    calls = []

    def mapper(operation, proposals):
        items = list(proposals)
        calls.extend(number for number, _ in items)
        return [operation(item) for item in items]

    operation, _, _ = probe.transform(probe.batch_seeds if parallel else mapper)
    expected = probe.discovery.fresh_discovery(baseline, 150., budget=budget)
    actual = operation(candidate, 150., budget=budget)
    assert calls == ([] if parallel else list(range(len(expected))))
    assert fingerprint(actual) == fingerprint(expected)


def test_batching_has_at_most_three_items_and_keeps_every_seed(monkeypatch):
    calls = []

    def run(operation, items):
        calls.append(list(items))
        return [operation(item) for item in items]

    monkeypatch.setattr(probe, 'map_predictive_folds', run)
    assert probe.batch_seeds(lambda item: item * 2, range(7)) == list(range(0, 14, 2))
    assert calls == [[0, 1, 2], [3, 4, 5], [6]]


def test_failed_batch_does_not_produce_an_incomplete_discovery(monkeypatch):
    def fail(operation, items):
        raise RuntimeError('child failed')

    monkeypatch.setattr(probe, 'map_predictive_folds', fail)
    with pytest.raises(RuntimeError, match='child failed'):
        probe.batch_seeds(lambda item: item, range(4))


@pytest.mark.parametrize('fail', [False, True])
def test_external_substitution_is_restored_after_success_or_failure(fail):
    original = probe.initial_search.fresh_discovery
    marker = object()
    try:
        with probe.selected_discovery(marker):
            assert probe.initial_search.fresh_discovery is marker
            if fail:
                raise RuntimeError('failed')
    except RuntimeError:
        assert fail
    assert probe.initial_search.fresh_discovery is original
