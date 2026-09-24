import json
from pathlib import Path

HERE = Path(__file__).parent


def test_fractional_four_group_coverage_and_post_seal_metrics():
    payload = json.loads((HERE / "fractional_per_track_evaluation.json").read_text())
    assert len(payload["rows"]) == 16
    assert {x["partition"] for x in payload["rows"]} == {"train", "validation"}
    assert all(
        x["held_used_for_fit"] is False and x["truth_used_for_fit"] is False
        for x in payload["rows"]
    )
    assert all(
        x["fractional_track_count"] > 0 and x["reference_error_km"] >= 0 for x in payload["rows"]
    )
