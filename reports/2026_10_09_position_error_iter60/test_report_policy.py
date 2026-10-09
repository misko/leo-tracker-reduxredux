from report_policy import ARMS, MODELS, compare_pairs, paired_indices, winner


def test_missing_arm_cannot_enter_paired_comparison():
    receipts = {(m, i, a): {} for m in MODELS for i in (0, 6) for a in ARMS}
    del receipts[("smooth", 6, "zero-c")]
    assert paired_indices([0, 6], receipts) == [0]


def test_winner_ignores_error_and_failed_fit_with_better_score():
    rows = [
        dict(index=i, error_km=e, fit=dict(objective=s, converged=c))
        for i, e, s, c in ((0, 0.1, 10, True), (6, 100, 9, True), (12, 0, 1, False))
    ]
    assert winner(rows)["index"] == 6
    assert winner([rows[2]]) is None


def test_failed_fit_is_not_counted_as_position_improvement():
    hard = [
        dict(index=0, error_km=100, fit=dict(converged=False)),
        dict(index=6, error_km=10, fit=dict(converged=True)),
    ]
    smooth = [
        dict(index=0, error_km=1, fit=dict(converged=True)),
        dict(index=6, error_km=11, fit=dict(converged=True)),
    ]
    counts = compare_pairs(hard, smooth)
    assert counts["gained_convergence"] == 1
    assert counts["regressed"] == 1
    assert counts["improved"] == 0
