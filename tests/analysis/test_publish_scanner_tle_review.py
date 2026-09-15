from copy import deepcopy

from tools.publish_scanner_tle_review import candidate_comparisons, concerns


def test_candidate_gains_preserve_training_leader_when_heldout_leader_changes():
    leader = {
        "catalog_number": 1,
        "name": "STARLINK-A",
        "training_rms_hz": 10,
        "heldout_rms_hz": 30,
        "tau_s": 1,
    }
    runner = {
        "catalog_number": 2,
        "name": "STARLINK-B",
        "training_rms_hz": 20,
        "heldout_rms_hz": 60,
        "tau_s": -1,
    }
    challenger = {
        "catalog_number": 3,
        "name": "STARLINK-C",
        "training_rms_hz": 40,
        "heldout_rms_hz": 15,
        "tau_s": 0,
    }
    rows = candidate_comparisons(
        {
            "fields": {
                "0": {"top_training": [leader, runner], "top_heldout": [challenger, leader, runner]}
            }
        }
    )
    assert [r["catalog_number"] for r in rows] == [1, 2, 3]
    assert rows[1]["leader_training_gain_hz"] == 10
    assert rows[1]["leader_heldout_gain_hz"] == 30
    assert rows[1]["leader_heldout_gain_percent"] == 50
    assert rows[2]["training_rank"] is None
    assert rows[2]["leader_heldout_gain_hz"] == -15
    assert rows[2]["leader_heldout_gain_percent"] == -100


def test_zero_rms_does_not_produce_infinite_gain():
    c = {
        "catalog_number": 1,
        "name": "STARLINK-A",
        "training_rms_hz": 0,
        "heldout_rms_hz": 0,
        "tau_s": 0,
    }
    rows = candidate_comparisons({"fields": {"0": {"top_training": [c], "top_heldout": [c]}}})
    assert rows[0]["leader_heldout_gain_hz"] == 0
    assert rows[0]["leader_heldout_gain_percent"] is None


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
