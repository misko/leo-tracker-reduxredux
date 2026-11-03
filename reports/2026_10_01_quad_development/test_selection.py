import pytest
from build_selection import chronological_quads, spread, evaluation_units, build


def fixture(n=12):
    captures = [dict(session_id=f's{i}', capture_start_utc_ns=i*420*10**9,
                     capture_end_utc_ns=(i*420+300)*10**9,
                     radio_id='radio', receiver_ids=[0,1]) for i in range(n)]
    candidates = [[0,c['capture_start_utc_ns'],c['radio_id'],c['session_id']] for c in captures]
    return captures, candidates


def test_missing_capture_breaks_continuity():
    captures, candidates = fixture()
    blocks, reasons = chronological_quads([c for c in captures if c['session_id'] != 's2'], candidates)
    assert [[c['session_id'] for c in b] for b in blocks] == [['s3','s4','s5','s6'], ['s7','s8','s9','s10']]
    assert reasons[0]['session_id'] == 's2'


@pytest.mark.parametrize('change', ['gap', 'overlap', 'radio', 'receivers'])
def test_boundaries_break_runs(change):
    captures, candidates = fixture(8)
    if change in ('gap', 'overlap'):
        delta = (1000 if change == 'gap' else -200)*10**9
        for c in captures[2:]:
            c['capture_start_utc_ns'] += delta
            c['capture_end_utc_ns'] += delta
    elif change == 'radio':
        for c in captures[2:]: c['radio_id'] = 'other'
    else:
        for c in captures[2:]: c['receiver_ids'] = [0]
    candidates = [[0,c['capture_start_utc_ns'],c['radio_id'],c['session_id']] for c in captures]
    blocks, _ = chronological_quads(captures, candidates)
    assert [c['session_id'] for c in blocks[0]] == ['s2','s3','s4','s5']


def test_determinism_and_duplicate_rejection():
    captures, candidates = fixture()
    assert chronological_quads(captures, candidates) == chronological_quads(captures[::-1], candidates[::-1])
    with pytest.raises(ValueError): chronological_quads(captures, candidates+candidates[:1])
    with pytest.raises(ValueError): chronological_quads(captures, candidates[:-1])
    assert spread(list(range(25)),6) == [0,4,9,14,19,24]
    with pytest.raises(ValueError): spread([1,2],3)


def test_nested_units_do_not_cross_blocks():
    rows = evaluation_units('block', ['a','b','c','d'])
    assert [r['scans'] for r in rows] == [['a'],['b'],['c'],['d'],['a','b'],['c','d'],['a','b','c','d']]
    assert all(r['block_id'] == 'block' for r in rows)


def test_real_selection_integrity():
    result = build()
    assert len(result['blocks']) == 16
    assert len(result['evaluation_units']) == 112
    assert len({r['session_id'] for r in result['captures']}) == 64
    assert set(c['dataset'] for c in result['captures']) == {'DS9','DS10','DS11'}
    assert all(0 <= gap <= 180 for b in result['blocks'] for gap in b['gaps_s'])
