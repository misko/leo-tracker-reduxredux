from search_progress import trajectory


def test_failed_better_score_never_improves_qualified_curve():
    rows = [dict(index=0, order=i, arm="fitted-c", fit=dict(
        elapsed_s=1, objective=score, converged=qualified))
        for i, (score, qualified) in enumerate([(10, True), (1, False), (9, True)])]
    assert [r["best_qualified_objective"] for r in trajectory(rows, "fitted-c")] == [10, 10, 9]


def test_no_qualified_state_remains_missing_not_zero():
    row = dict(index=0, order=0, arm="zero-c", fit=dict(
        elapsed_s=2, objective=1, converged=False))
    assert trajectory([row], "zero-c") == [dict(fit_seconds=2, best_qualified_objective=None)]
