from copy import deepcopy

from tools.publish_scanner_tle_review import concerns


def track():
    winner = {
        "tau_s": 0,
        "training_rms_hz": 1,
        "heldout_rms_hz": 2,
        "exact_center_validation": {"heldout_rms_hz": 2, "minimum_elevation_deg": 10},
    }
    control = deepcopy(winner)
    control["exact_center_validation"]["heldout_rms_hz"] = 10
    return {
        "fields": {
            "0": {"top_training": [winner], "top_heldout": [winner], "winner_heldout_rank": 1},
            "-500": {"top_training": [control]},
            "500": {"top_training": [control]},
        },
        "radio_polynomials": [{"heldout_rms_hz": 3}, {"heldout_rms_hz": 4}],
    }


def test_descriptive_check_requires_beating_both_radio_models():
    t = track()
    assert concerns(t) == []
    t["radio_polynomials"][0]["heldout_rms_hz"] = 1
    assert "radio drift fits as well or better" in concerns(t)


def test_horizon_and_wrong_time_failures_are_retained():
    t = track()
    t["fields"]["0"]["top_training"][0]["exact_center_validation"]["minimum_elevation_deg"] = -1
    t["fields"]["500"]["top_training"][0]["exact_center_validation"]["heldout_rms_hz"] = 1
    assert "below horizon during support" in concerns(t)
    assert "500s control fits as well or better" in concerns(t)


def test_exact_candidate_tie_does_not_pass():
    t = track()
    t["fields"]["0"]["top_training"] *= 2
    assert "training candidate tie" in concerns(t)
