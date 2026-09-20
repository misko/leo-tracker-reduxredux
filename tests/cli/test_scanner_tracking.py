from pathlib import Path

import leo.cli.scanner_tracking as scanner_tracking


def test_review_renderer_bounds_report_before_expensive_track_work(
    tmp_path: Path, monkeypatch
) -> None:
    observed = {}

    def build_report(session_id, output, **kwargs):
        observed.update(kwargs)
        filename = "review.png"
        (output / filename).write_bytes(b"png")
        return {
            "tracks": [
                {
                    "tracklet_id": "sha256:" + "1" * 64,
                    "channel": 1,
                    "edge": "lower",
                    "start_s": 1.0,
                    "end_s": 9.0,
                    "observation_count": 14,
                    "training_count": 8,
                    "heldout_count": 6,
                    "candidates": [
                        {
                            "standard_rank": 1,
                            "catalog_number": 60_001,
                            "selected_tau_s": 0.0,
                            "offset_hz": 10.0,
                            "offset_only_training_rms_hz": 20.0,
                            "offset_only_heldout_rms_hz": 30.0,
                        }
                    ],
                }
            ],
            "track_figures": [filename],
            "track_limit_reached": True,
        }

    monkeypatch.setattr(scanner_tracking, "build_report", build_report)

    rendered = scanner_tracking._review_renderer(
        bulk_root=tmp_path, tle_root=tmp_path, site_name="spinnaker-sausalito"
    )("scan-test")

    assert observed["maximum_tracks"] == 32
    reviews, limit_reached = rendered
    assert limit_reached is True
    assert len(reviews) == 1
    assert reviews[0][0].artifact_name == "tle-review-01"
    assert reviews[0][1] == b"png"
