"""Contract checks for the sealed full-catalogue blind artifact."""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def test_blind_artifact_is_reference_free_and_complete() -> None:
    document = json.loads((HERE / "blind-inference.json").read_text())
    assert document["schema"] == "ds2-lt3d-geometry-cone-blind-reassociated-inference/v1"
    assert document["complete"] is True
    assert document["reference_used_for_inference"] is False
    assert "site-assisted" not in document["identity_scope"]
    assert document["full_fov_deg"] == [10, 20, 25, 30, 40, 50, 60, 70, 80, 90]
    assert document["local_fitted_full_fov_deg"] == [10, 20, 25, 30, 40, 50]
    assert document["fixed_half_angle_deg"] == [10, 15, 20, 30]
    assert len(document["results"]) == 4
    for result in document["results"]:
        assert result["baseline"]["converged"]
        assert len(result["staged_full_fov"]["scenarios"]) == 10
        assert set(result["fixed_hard_half_angle"]) == {"10", "15", "20", "30"}
        assert set(result["local_fitted_cone"]["winners"]) == {
            "10",
            "20",
            "25",
            "30",
            "40",
            "50",
        }
