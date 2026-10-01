import pytest
from screen_seed_prefix import summarize_receipt


def receipt():
    fits = [dict(seed_index=0, objectives=[5.], converged=True, seconds=2., mean=[0., 0.]),
            dict(seed_index=1, objectives=[4.], converged=False, seconds=3., mean=[1., 0.])]
    return dict(unit='test', binding={'size': 2}, fits=fits, best=fits[1], wall_seconds=12.)


def test_unresolved_lower_objective_is_not_replaced_by_converged_fit():
    row = summarize_receipt(receipt())
    assert row['winner_index'] == 1
    assert row['first_solver_converged'] and not row['best_solver_converged']
    assert row['objective_gap'] == 1.
    assert row['position_difference_m'] == 1000.
    assert row['omitted_recorded_fit_seconds'] == 3.


def test_missing_first_start_and_changed_winner_rejected():
    r = receipt()
    r['fits'][0]['seed_index'] = 2
    with pytest.raises(ValueError):
        summarize_receipt(r)
    r = receipt()
    r['best'] = r['fits'][0]
    with pytest.raises(ValueError):
        summarize_receipt(r)
