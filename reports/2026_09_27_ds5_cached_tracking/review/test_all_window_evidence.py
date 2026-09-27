import pytest

from all_window_evidence import select_cases


def test_complete_membership_and_chronology():
    cases = [dict(case_id=str(i), session_id='s', visit_index=i, split='dev',
                  is_holdout=False, evaluation_role='newdevelopment') for i in (3, 1, 2)]
    assert [c['visit_index'] for c in select_cases({'cases': cases})] == [1, 2, 3]
    with pytest.raises(ValueError, match='duplicate'):
        select_cases({'cases': cases + [cases[0]]})
    cases[0]['is_holdout'] = True
    with pytest.raises(ValueError, match='development-only'):
        select_cases({'cases': cases})
