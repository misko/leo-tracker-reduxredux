from copy import deepcopy

import numpy as np
import pytest

from leo.analysis.localization_v3 import initial_search as search
from leo.analysis.localization_v5.initial_control import initial_control
from tests.analysis.test_localization_v3_position import prepared


def test_complete_real_fit_reuse_eliminates_two_fits_and_preserves_entire_search(monkeypatch):
    from check_algo07v3_scan_likelihood import fingerprint

    from leo.analysis.localization_v3 import position

    calls = []
    original = position.fit

    def measured(*args, **kwargs):
        calls.append(kwargs.get('iterations'))
        return original(*args, **kwargs)

    monkeypatch.setattr(position, 'fit', measured)
    monkeypatch.setattr(search, 'fit', measured)
    budgets = dict(seed_budget=1, branch_budget=1, rounds=2, iterations=2)
    scan, _ = prepared()
    expected = search.initial_search(scan, 150., **budgets)
    assert calls == [2] * 6
    calls.clear()
    scan, _ = prepared()
    actual = search.initial_search(scan, 150., initial_control=initial_control, **budgets)
    assert calls == [2] * 4
    assert fingerprint(actual) == fingerprint(expected)
    winner = actual['choices'][actual['selected_hypothesis']]
    before = fingerprint(winner)
    for arm in ('c0', 'fitted_c'):
        control = actual['zero_phase_control'][arm]
        control['parameters'][0] = 999
        control['history'][0]['parameters'][0] = 999
        control['score'] = 999
    assert fingerprint(winner) == before


@pytest.mark.parametrize('failure', [
    'epoch', 'reference', 'start', 'reference_shape', 'start_shape',
])
def test_nonzero_or_invalid_first_round_cannot_be_reused(failure):
    first = dict(epoch=0, phase_reference=np.zeros(1),
                 fit=dict(history=[dict(parameters=np.zeros(2))]))
    if failure == 'epoch':
        first['epoch'] = 1
    elif failure == 'reference':
        first['phase_reference'][0] = 1
    elif failure == 'start':
        first['fit']['history'][0]['parameters'][0] = 1
    elif failure == 'reference_shape':
        first['phase_reference'] = np.zeros((1, 1))
    else:
        first['fit']['history'][0]['parameters'] = np.zeros(3)
    winner = dict(arms=dict(c0=dict(phase_rounds=[deepcopy(first)])))
    with pytest.raises(ValueError, match='epoch zero'):
        initial_control(winner, 'c0')
