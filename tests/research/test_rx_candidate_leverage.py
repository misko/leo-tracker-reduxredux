import math

import pytest

from tools.rx_candidate_leverage import summarize


def test_concentration_preserves_zero_support_and_omitted_mass():
    bank = {
        "tracks": [
            {
                "session_id": "s",
                "track_id": str(i),
                "retained_catalogue_probability_mass": 0.9,
                "top_candidates": [
                    {"catalog_number": j, "conditional_top3_probability": p}
                    for j, p in enumerate(weights)
                ],
            }
            for i, weights in enumerate(([1.0, 0.0, 0.0], [0.5, 0.5, 0.0]))
        ]
    }
    partitions = {"recordings": [{"session_id": "s", "recording_split": "evaluation"}]}
    result = summarize(bank, partitions)
    assert result["tracks"][0]["effective_candidate_count"] == 1
    assert result["tracks"][1]["effective_candidate_count"] == pytest.approx(2)
    assert result["tracks"][1]["conditional_entropy_nats"] == pytest.approx(math.log(2))
    assert result["groups"]["evaluation"]["exact_unit_top_weight"] == 1
    assert result["groups"]["all"]["maximum_omitted_catalogue_mass"] == pytest.approx(0.1)


def test_invalid_posterior_rejected():
    bank = {
        "tracks": [{"session_id": "s", "top_candidates": [{"conditional_top3_probability": 0.7}]}]
    }
    with pytest.raises(ValueError, match="sum"):
        summarize(bank, {"recordings": [{"session_id": "s", "recording_split": "evaluation"}]})
