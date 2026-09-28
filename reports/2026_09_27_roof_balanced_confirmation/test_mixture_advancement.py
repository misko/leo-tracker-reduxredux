from copy import deepcopy

import pytest

from mixture_advancement import evaluate_gate

SESSIONS = [f"scan{i}" for i in range(6)]


def folds(gains=None, counts=None):
    gains = gains or [1.] * 6
    counts = counts or [10] * 6
    return [{"session_id": sid, "track_count": n, "models": {
        "M0": {"joint_nll_sum": 12. * n, "converged": True},
        "mean": {"joint_nll_sum": 10. * n, "converged": True},
        "mixture": {"joint_nll_sum": 10. * n - gain, "converged": True},
    }} for sid, n, gain in zip(SESSIONS, counts, gains, strict=True)]


def test_balanced_gain_passes_and_order_does_not_matter():
    result = evaluate_gate(folds(), SESSIONS)
    assert result["advance"] and result["improving_scans"] == 6
    assert result == evaluate_gate(list(reversed(folds())), SESSIONS)


def test_one_scan_cannot_carry_apparent_improvement():
    result = evaluate_gate(folds([100., .1, .1, .1, -1., -1.]), SESSIONS)
    assert result["checks"]["at_least_four_scans_improve"]
    assert result["checks"]["pooled_better_than_mean"]
    assert not result["advance"]
    assert "positive_after_removing_largest_gain" in result["failed_checks"]


def test_pooling_weights_tracks_not_scans():
    result = evaluate_gate(folds([1., 1., 1., 1., 1., -20.], [1, 1, 1, 1, 1, 100]), SESSIONS)
    assert result["improving_scans"] == 5
    assert not result["checks"]["pooled_better_than_mean"]
    assert result["pooled_nll_per_track"]["mixture"] == pytest.approx(10. + 15. / 105.)


def test_nonconvergence_and_machine_noise_cannot_advance():
    rows = folds()
    rows[0]["models"]["M0"]["converged"] = False
    assert not evaluate_gate(rows, SESSIONS)["advance"]
    assert not evaluate_gate(folds([1e-10] * 6), SESSIONS)["advance"]


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "nan", "count", "model"])
def test_malformed_evidence_rejected(mutation):
    rows = deepcopy(folds())
    if mutation == "missing": rows.pop()
    elif mutation == "duplicate": rows[0]["session_id"] = rows[1]["session_id"]
    elif mutation == "nan": rows[0]["models"]["mixture"]["joint_nll_sum"] = float("nan")
    elif mutation == "count": rows[0]["track_count"] = 0
    else: del rows[0]["models"]["mean"]
    with pytest.raises(ValueError): evaluate_gate(rows, SESSIONS)
