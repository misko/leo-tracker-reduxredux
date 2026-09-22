from pathlib import Path
from types import SimpleNamespace

import pytest

import leo.cli.scanner_tracking as scanner_tracking


def test_position_method_publication_is_reread_before_reporting_complete(
    tmp_path: Path, monkeypatch
) -> None:
    digest = "sha256:" + "1" * 64
    monkeypatch.setattr(
        scanner_tracking,
        "run_position_methods",
        lambda *_args, **_kwargs: SimpleNamespace(
            document=SimpleNamespace(input_manifest_sha256=digest)
        ),
    )
    observed = []
    monkeypatch.setattr(
        scanner_tracking,
        "position_methods_complete",
        lambda *_, **kwargs: observed.append(kwargs) or True,
    )

    scanner_tracking._publish_position_methods_verified(
        bulk_root=tmp_path,
        tle_root=tmp_path / "tle",
        session_id="scan-test",
        input_manifest_sha256=digest,
    )
    assert observed == [{"expected_input_manifest_sha256": digest}]


def test_position_method_publication_rejects_unverified_or_stale_output(
    tmp_path: Path, monkeypatch
) -> None:
    digest = "sha256:" + "1" * 64
    monkeypatch.setattr(
        scanner_tracking,
        "run_position_methods",
        lambda *_args, **_kwargs: SimpleNamespace(
            document=SimpleNamespace(input_manifest_sha256=digest)
        ),
    )
    monkeypatch.setattr(scanner_tracking, "position_methods_complete", lambda *_, **__: False)
    with pytest.raises(ValueError, match="completion verification"):
        scanner_tracking._publish_position_methods_verified(
            bulk_root=tmp_path,
            tle_root=tmp_path / "tle",
            session_id="scan-test",
            input_manifest_sha256=digest,
        )

    monkeypatch.setattr(
        scanner_tracking,
        "run_position_methods",
        lambda *_args, **_kwargs: SimpleNamespace(
            document=SimpleNamespace(input_manifest_sha256="sha256:" + "2" * 64)
        ),
    )
    with pytest.raises(ValueError, match="completion verification"):
        scanner_tracking._publish_position_methods_verified(
            bulk_root=tmp_path,
            tle_root=tmp_path / "tle",
            session_id="scan-test",
            input_manifest_sha256=digest,
        )


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
            "eligible_track_count": 1,
        }

    monkeypatch.setattr(scanner_tracking, "build_report", build_report)

    rendered = scanner_tracking._review_renderer(
        bulk_root=tmp_path,
        tle_root=tmp_path,
        site_name="spinnaker-sausalito",
        review_limit=64,
    )("scan-test")

    assert observed["maximum_tracks"] == 64
    reviews, eligible_count = rendered
    assert eligible_count == 1
    assert len(reviews) == 1
    assert reviews[0][0].artifact_name == "tle-review-01"
    assert reviews[0][1] == b"png"
