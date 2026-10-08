from additive_policy import select


def test_selection_retains_baseline_on_ties_or_nonconvergence_without_using_error():
    baseline = dict(selection_score=10, converged=True, horizontal_error_m=100000)
    better_error_worse_score = dict(selection_score=11, converged=True, horizontal_error_m=1)
    assert select(baseline, better_error_worse_score) == (baseline, "baseline")
    tie = dict(selection_score=10, converged=True, horizontal_error_m=1)
    assert select(baseline, tie) == (baseline, "baseline")
    nonstationary = dict(selection_score=9, converged=False, horizontal_error_m=1)
    assert select(baseline, nonstationary) == (baseline, "baseline")
    lower = dict(selection_score=9, converged=True, horizontal_error_m=200000)
    assert select(baseline, lower) == (lower, "additional")
    assert select(baseline, None) == (baseline, "baseline")
