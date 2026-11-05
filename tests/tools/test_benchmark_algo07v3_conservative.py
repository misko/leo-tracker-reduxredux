import pytest
from benchmark_algo07v3_conservative import trials


def test_alternates_exact_complete_stages_and_records_child_cpu():
    calls = []

    def run(side):
        calls.append(side)
        return dict(result=1)

    rows = trials({s: lambda s=s: run(s) for s in ('baseline', 'candidate')}, dict(result=1), 3)
    assert calls == ['baseline', 'candidate', 'candidate', 'baseline', 'baseline', 'candidate']
    assert len(rows) == 6 and all(r['exact'] and r['completed'] for r in rows)
    assert all(r['self_cpu_seconds'] >= 0 and r['children_cpu_seconds'] >= 0 for r in rows)


def test_changed_stage_cannot_produce_an_exact_receipt():
    with pytest.raises(ValueError, match='Conservative science differs'):
        trials(dict(baseline=lambda: 1, candidate=lambda: 2), 1, 1)


def test_unbounded_component_repeat_is_rejected_before_work():
    with pytest.raises(ValueError, match='bounded'):
        trials({}, None, 4)
