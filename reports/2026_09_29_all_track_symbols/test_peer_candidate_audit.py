from peer_candidate_audit import choose


def test_selection_ignores_evaluation_outcome():
    a = dict(candidate_rank=2, calibration_median=0.4, evaluation_median=0.99)
    b = dict(candidate_rank=1, calibration_median=0.5, evaluation_median=0.01)
    assert choose([a, b]) is b
    a["evaluation_median"] = 0
    b["evaluation_median"] = 1
    assert choose([a, b]) is b


def test_selection_tie_uses_candidate_rank():
    a = dict(candidate_rank=2, calibration_median=0.5)
    b = dict(candidate_rank=1, calibration_median=0.5)
    assert choose([a, b]) is b
