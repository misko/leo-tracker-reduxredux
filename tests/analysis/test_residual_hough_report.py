from __future__ import annotations

import json
from pathlib import Path

_REPORT = Path("reports/2026_08_22_residual_hough_segmentation.md")
_FIGURES = Path("reports/figures/2026_08_22_residual_hough_segmentation")


def test_report_manifest_binds_both_capture_results_and_honest_replay_status() -> None:
    manifest = json.loads((_FIGURES / "manifest.json").read_bytes())
    reports = {item["session_id"]: item for item in manifest["reports"]}

    first = reports["cap-20260821T201522-841b2a20e151"]
    second = reports["cap-20260822T002522-4d536888cfbc"]
    assert first["selection"]["selected_line_count"] == 4
    assert second["selection"]["selected_line_count"] == 2
    assert first["trajectory_replay_v3"]["status"] == "complete"
    assert first["trajectory_replay_v3"]["replay_result_count"] == 4_704
    assert second["trajectory_replay_v3"] == {
        "status": "blocked_raw_integrity",
        "error_type": "BundleCorruptionError",
        "detail": second["trajectory_replay_v3"]["detail"],
        "verification_bypassed": False,
    }
    assert "iq-000007.ci16.zst" in second["trajectory_replay_v3"]["detail"]


def test_report_pipeline_products_are_linear_versioned_and_rendered() -> None:
    report_text = _REPORT.read_text()
    for pipeline_json in sorted(_FIGURES.glob("*-pipeline-segmentation.json")):
        bank = json.loads(pipeline_json.read_bytes())
        assert bank["schema_version"] == 2
        assert bank["algorithm_version"] == "alternate-cfo-residual-hough-v2"
        assert bank["configuration"]["minimum_split_gain"] == 200.0
        assert all(track["acceleration_hz_per_s2"] == 0.0 for track in bank["tracks"])
        strongest_parent = bank["parent_selections"][0]["parent_track_id"]
        strongest_count = bank["parent_selections"][0]["selected_line_count"]
        assert all(
            track["source_parent_track_id"] == strongest_parent
            for track in bank["tracks"][:strongest_count]
        )
        png = pipeline_json.with_suffix(".png")
        assert png.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        assert png.name in report_text

    replay = json.loads(
        (
            _FIGURES / "cap-20260821T201522-841b2a20e151-stream-0-RX1-trajectory-replay-v3.json"
        ).read_bytes()
    )
    bank = replay["trajectory_bank"]
    assert bank["schema_version"] == 3
    assert bank["algorithm_version"] == "standard-trajectory-bank-v3"
    assert {item["polynomial_degree"] for item in bank["trajectories"]} == {1}
    assert replay["replay_preserved"] is True
