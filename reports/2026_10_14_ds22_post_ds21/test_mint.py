"""Offline checks for whole-acquisition boundaries and outcome-free inclusion."""

import importlib.util
import json
from pathlib import Path

SOURCE = Path(__file__).with_name("raw_inventory.py")
spec = importlib.util.spec_from_file_location("ds21_raw", SOURCE)
raw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(raw)


def recording(root, name, times, channels=(1, 2), status="incomplete"):
    for i, time in enumerate(times):
        path = root / name / f"segment-{i}"
        path.mkdir(parents=True)
        index = b'{"channel":1}\n'
        (path / "index.jsonl").write_bytes(index)
        (path / "iq.zst").write_bytes(b"iq")
        document = dict(
            kind="short_window_iq_recording",
            created_utc_ns=time,
            configuration={"targets": [{"channel": c} for c in channels]},
            status=status,
            window_count=1,
            chunks=[
                dict(
                    compressed_sha256=f"iq-{name}-{i}",
                    index_sha256=raw.digest(index),
                    index_relative_path="index.jsonl",
                    payload_relative_path="iq.zst",
                    compressed_bytes=2,
                )
            ],
        )
        (path / "manifest.json").write_text(json.dumps(document))


def test_whole_recording_cutoff_incomplete_and_non_eight_channels(tmp_path):
    root = tmp_path / "raw"
    recording(root, "straddles", [9, 11])
    recording(root, "boundary", [10])
    recording(root, "new", [11, 12])
    recording(root, "future", [21])
    result = raw.inventory(
        [root], tmp_path / "analysis", 20, start_ns=11, dataset_id="DS21", required_channels=None
    )
    assert result["dataset_id"] == "DS21"
    assert [r["recording_id"] for r in result["members"]] == ["new"]
    assert result["counts"]["incomplete"] == 1
    assert result["members"][0]["window_count"] == 2
    assert not result["members"][0]["tracking_inputs"]
    assert not result["members"][0]["raw_recording"]["integrity_errors"]


def test_raw_copies_are_deduplicated(tmp_path):
    import shutil

    root = tmp_path / "raw"
    recording(root, "new", [11])
    shutil.copytree(root / "new", root / "copy")
    result = raw.inventory(
        [root], tmp_path / "analysis", 20, start_ns=11, dataset_id="DS21", required_channels=None
    )
    assert len(result["members"]) == 1
    assert len(result["members"][0]["raw_recording"]["duplicate_roots"]) == 1


def test_adaptive_wrapper_capture_time_and_missing_payload_are_retained(tmp_path):
    from mint import legacy_member

    d = dict(
        kind="starlink_adaptive_hop_iq",
        session_id="adaptive",
        created_utc_ns=12,
        timing={"first_sample_estimate_utc_ns": 11},
        chunks=[
            dict(
                relative_path="missing.zst",
                compressed_sha256="compressed",
                uncompressed_sha256="raw",
                compressed_bytes=2,
            )
        ],
        receipt=dict(
            terminal={"reason": "interrupted"},
            retained_visit_indices=[0],
            plan={"geometry": {"profiles": [{"target": {"channel": 1}}]}},
        ),
    )
    result = legacy_member(
        dict(path=str(tmp_path / "manifest.json"), sha256="manifest", document={"manifest": d})
    )
    assert result["captured_utc_ns"] == 11
    assert result["recording_state"] == "incomplete"
    assert result["raw_recording"]["integrity_errors"]
    assert result["window_count"] == 1


def test_unknown_new_format_is_not_silently_omitted(tmp_path):
    import pytest
    from mint import legacy_member

    with pytest.raises(ValueError, match="unrecognized"):
        legacy_member(dict(path=str(tmp_path / "manifest.json"), document={"kind": "unknown"}))
