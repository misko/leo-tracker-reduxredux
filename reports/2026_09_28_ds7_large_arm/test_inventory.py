"""The frozen larger cohort must not silently shrink or reuse the smoke set."""
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent


def test_complete_frozen_cohort_is_unique_and_disjoint_from_smoke():
    plan = json.loads((HERE / 'plan.json').read_text())
    inputs = json.loads((HERE / 'inputs.json').read_text())
    smoke = json.loads((HERE.parent / '2026_09_28_ds7_glrt_benchmark/inputs.json').read_text())
    expected = []
    assert len(plan['captures']) == len({c['session_id'] for c in plan['captures']}) == 88
    for capture in plan['captures']:
        indices = capture['visit_indices']
        assert len(indices) == len(set(indices)) == 8
        assert indices == sorted(indices)
        assert all(0 <= index < capture['visits'] for index in indices)
        expected.extend((capture['session_id'], index) for index in indices)
    observed = [(row['session_id'], row['visit_index']) for row in inputs['rows']]
    old = {(row['session_id'], row['visit_index']) for row in smoke['rows']}
    assert inputs['complete'] is True
    assert observed == expected
    assert len(observed) == len(set(observed)) == 704
    assert not set(observed) & old
    assert {r['target_index'] for r in inputs['rows']} == set(range(8))
    assert {r['rate_hz'] for r in inputs['rows']} == {2500000, 5000000, 7500000, 10000000}
