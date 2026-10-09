from selection import winner


def row(order, score, converged=True, error=0, arm="fitted-c"):
    return dict(
        order=order, arm=arm, fit=dict(objective=score, converged=converged), error_km=error
    )


def test_score_and_convergence_ignore_reference_accuracy():
    rows = [row(0, 10, error=100), row(1, 20, error=0), row(2, 0, converged=False)]
    assert winner(rows, "fitted-c") is rows[0]
    rows[0]["error_km"], rows[1]["error_km"] = 0, 10000
    assert winner(rows, "fitted-c") is rows[0]


def test_ties_keep_earlier_candidate_and_arms_are_separate():
    rows = [row(1, 10), row(0, 10), row(2, -1, arm="zero-c")]
    assert winner(rows, "fitted-c") is rows[1]
    assert winner(rows, "zero-c") is rows[2]


def test_no_qualified_fit_returns_none():
    assert winner([row(0, 0, converged=False)], "fitted-c") is None
