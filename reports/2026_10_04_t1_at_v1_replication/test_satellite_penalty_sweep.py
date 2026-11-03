import copy

import numpy as np
import pytest

from satellite_penalty_sweep import BUDGET, engine, validate_score
from seed_restart_pipeline import POSITION_BUDGET


def toy_mode(number, count, start):
    rows = np.arange(start, start+count)
    return dict(catalog_number=number, offset_s=0., rows=rows,
                lanes=[(rows, np.zeros(count))])


@pytest.mark.parametrize('penalty,expected', [(5, 22), (10, 12), (15, 0)])
def test_only_penalty_changes_admission_and_keeps_minimum_support(penalty, expected):
    _, Search = engine()
    modes = [toy_mode(1, 12, 0), toy_mode(2, 10, 12), toy_mode(3, 9, 22)]
    groups = np.arange(31); times = np.arange(31, dtype=float)
    result = Search(modes, groups, times, penalty=penalty).run(3)
    # Penalty 10 accepts only the 12-window track; penalty 5 accepts 12+10.
    assert result['final']['assigned'] == expected
    assert 3 not in [r['catalog_number'] for r in result['final']['selected']]
    validate_score(result, penalty)
    assert result['converged']


def test_score_validation_rejects_wrong_penalty_and_duplicate_windows():
    _, Search = engine()
    result = Search([toy_mode(1, 12, 0)], np.arange(12), np.arange(12.), penalty=5).run(3)
    with pytest.raises(ValueError, match='Wrong satellite penalty'):
        validate_score(result, 15)
    bad = copy.deepcopy(result)
    bad['final']['assignments'][1]['row_index'] = bad['final']['assignments'][0]['row_index']
    with pytest.raises(ValueError, match='Duplicate'):
        validate_score(bad, 5)
    assert BUDGET == POSITION_BUDGET
