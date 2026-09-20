from tools.plot_recent_tle_rms import pair


def test_evaluation_rank_reversal_is_not_hidden_by_reselecting_winner():
    result = pair(
        {
            "candidates": [
                {"rank": 2, "catalog_number": 22, "randomized_evaluation_rms_hz": 10},
                {"rank": 1, "catalog_number": 11, "randomized_evaluation_rms_hz": 50},
            ]
        }
    )
    assert result["best_norad"] == 11
    assert result["best_rms_hz"] == 50
    assert result["runner_rms_hz"] == 10


def test_single_candidate_has_no_pair():
    assert pair({"candidates": []}) is None
