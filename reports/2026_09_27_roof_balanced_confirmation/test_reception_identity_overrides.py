import math

import pytest

from reception_identity_overrides import track_override


def fixture():
    return {"candidate_ids": [1, 2], "track_id": "track", "weight_seconds": 20,
            "reserve_observations": 12, "log_weights": [0., -3.],
            "variants": {"mixture": {
                "frequency_map_candidate_id": 1, "joint_map_candidate_id": 2,
                "candidate_frequency_log_likelihood": [-10., -12.],
                "candidate_detection_log_likelihood": [-8., -2.],
                "candidate_ratio_log_likelihood": [-4., -2.],
                "joint_posterior_log_weights": [-math.log1p(math.exp(3)), -math.log1p(math.exp(-3))],
                "frequency_posterior_log_weights": [-math.log1p(math.exp(-5)), -math.log1p(math.exp(5))],
                "matched_reception_observations": 7}}}


def test_override_decomposition():
    row = track_override(fixture())
    assert row["changed"]
    assert row["log_evidence_joint_choice_minus_frequency_choice"] == {
        "training": -3., "frequency": -2., "detection": 6., "ratio": 2.}
    assert row["frequency_probability_of_joint_choice"] < .01
    assert row["joint_probability_of_joint_choice"] > .95


def test_no_override():
    track = fixture()
    track["variants"]["mixture"]["joint_map_candidate_id"] = 1
    assert not track_override(track)["changed"]


def test_corrupt_evidence_rejected():
    track = fixture()
    track["variants"]["mixture"]["candidate_ratio_log_likelihood"][0] = -99.
    with pytest.raises(ValueError, match="posterior odds"):
        track_override(track)
