import pytest
from benchmark_algo07v3_grid import compare_grids


def test_complete_grid_comparison_checks_every_value_but_allows_elapsed_time():
    calls, records = [], []
    port = object()
    def original(score, endpoints, **kwargs):
        assert 'map_batches' not in kwargs
        calls.append('baseline')
        return dict(complete=True, evaluated_points=1, scores=[score()], elapsed_seconds=1.)
    def candidate(score, endpoints, **kwargs):
        assert kwargs['map_batches'] is port
        calls.append('candidate')
        return dict(complete=True, evaluated_points=1, scores=[score()], elapsed_seconds=2.)
    value = compare_grids(original, candidate, lambda: 3., {}, dict(map_batches=port),
                          lambda rows: records.append(list(rows)))
    assert calls == ['baseline', 'candidate', 'candidate', 'baseline', 'baseline', 'candidate']
    assert len(records[-1]) == 6 and all(r['exact'] for r in records[-1])
    assert value['scores'] == [3.]


@pytest.mark.parametrize('fault', ['incomplete', 'changed'])
def test_partial_or_changed_grid_is_not_qualified(fault):
    def original(*a, **k):
        return dict(complete=True, evaluated_points=1, scores=[3.])
    def candidate(*a, **k):
        return dict(complete=fault != 'incomplete', evaluated_points=1, scores=[4.])
    with pytest.raises(ValueError, match='Incomplete|changed'):
        compare_grids(original, candidate, None, {}, {}, lambda rows: None)
