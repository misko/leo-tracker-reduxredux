import pytest
from benchmark_algo07v3_screen_geometry import trials


def test_alternates_sides_and_compares_every_complete_screen():
    calls = []

    def function(side):
        def run(value):
            calls.append(side)
            return dict(result=value)
        return run

    rows = trials({s: function(s) for s in ('baseline', 'candidate')}, [17], dict(result=17), 3)
    assert calls == ['baseline', 'candidate', 'candidate', 'baseline', 'baseline', 'candidate']
    assert len(rows) == 6 and all(r['exact'] for r in rows)


def test_wrong_screen_cannot_produce_a_timing_receipt():
    with pytest.raises(ValueError, match='Complete screen differs'):
        trials(dict(baseline=lambda: 1, candidate=lambda: 2), [], 1, 1)


def test_unbounded_repetition_is_rejected_before_work():
    with pytest.raises(ValueError, match='bounded'):
        trials({}, [], None, 6)
