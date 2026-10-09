from policy import select


def row(index, arm, objective, qualified, error):
    return dict(
        index=index,
        order=0,
        arm=arm,
        fit=dict(objective=objective, converged=qualified, error_km=error),
    )


def test_low_error_does_not_select_retry():
    rows = [
        row(1, "fitted-c", 10, True, 100),
        row(2, "fitted-c", 11, False, 0),
        row(3, "fitted-c", 9, False, 100),
        row(4, "zero-c", 8, True, 100),
        row(5, "zero-c", 12, False, 0),
    ]
    assert [r["index"] for r in select(rows)] == [1, 3, 4]


def test_score_ties_use_frozen_index_not_truth():
    rows = [
        row(2, "fitted-c", 10, True, 0),
        row(1, "fitted-c", 10, True, 100),
        row(4, "zero-c", 8, True, 0),
    ]
    assert [r["index"] for r in select(rows)] == [1, 4]
