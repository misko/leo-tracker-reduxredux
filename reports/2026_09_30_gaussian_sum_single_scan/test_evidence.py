import importlib.util
import json
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("gaussian_evidence", HERE / "evidence.py")
assert SPEC and SPEC.loader
evidence = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evidence)


def test_selection_is_exact_and_bound_to_authorities():
    selected = evidence.freeze_selection()
    assert selected["counts"] == {"DS9": 8, "DS10": 8, "DS11": 32}
    assert [row["selection_index"] for row in selected["selected"]["DS9"]] == [0, 14, 29, 44, 59, 74, 89, 104]
    assert selected["selected"]["DS10"][0]["session_id"] == "scan-fw-b1078e5fd8cd5b5e"
    assert selected["selected"]["DS11"][-1]["session_id"] == "scan-fw-8165310e3c4e205a"
    assert all(item["sha256"].startswith("sha256:") for item in selected["authorities"].values())


def test_loader_orders_completed_tracks_and_excludes_truth(tmp_path):
    source = tmp_path / "observations.json"
    source.write_text(json.dumps({
        "schema":"ds7-baseline-track-export/v1", "session_id":"scan-x", "manifest_sha256":"sha256:m",
        "analysis_manifest_sha256":"sha256:a", "start_utc_ns":1000, "sample_rate_hz":1,
        "snapshot_sha256":"sha256:s", "evidence_sha256":"sha256:e", "tracks":[
          {"track_id":"sha256:b", "times_s":[1,3], "measured_hz":[2,1], "receiver_id":1,"channel":2,"rf_hz":11,"visits":[2,4]},
          {"track_id":"sha256:a", "times_s":[0,2], "measured_hz":[3,2], "receiver_id":0,"channel":2,"rf_hz":11,"visits":[1,3]}
        ], "pose":{"latitude":99}, "winning_norad":123
    }))
    result = evidence.load_observation_export(source, {"session_id":"scan-x", "manifest_sha256":"sha256:m"})
    assert [row["track_id"] for row in result["tracks"]] == ["sha256:a", "sha256:b"]
    assert result["tracks"][0]["times_utc_ns"] == [1000, 2_000_001_000]
    assert result["tracks"][0]["uncertainty"]["covariance_hz2"] is None
    assert "pose" not in result and "winning_norad" not in result
    assert result["candidate_bank"] is None


def test_loader_rejects_duplicate_or_noncausal_observations(tmp_path):
    source = tmp_path / "bad.json"
    doc = {"schema":"ds7-baseline-track-export/v1", "session_id":"s", "manifest_sha256":"m",
      "analysis_manifest_sha256":"a", "start_utc_ns":0, "sample_rate_hz":1,
      "snapshot_sha256":"s", "evidence_sha256":"e", "tracks":[
        {"track_id":"t", "times_s":[1,1], "measured_hz":[0,0], "receiver_id":0,"channel":0,"rf_hz":1,"visits":[1,2]}]}
    source.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="non-increasing"):
        evidence.load_observation_export(source)


def test_frozen_selection_matches_checked_in_file():
    assert json.loads((HERE / "selection.json").read_text()) == evidence.freeze_selection()
