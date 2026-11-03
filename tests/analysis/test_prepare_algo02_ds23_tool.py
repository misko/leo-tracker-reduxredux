"""Manifest binding and immutable scientific input checks for ALGO02 exports."""

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import prepare_algo02_ds23 as module


def fixture(tmp_path):
    payload = tmp_path / "public.json"
    payload.write_text('{"existing": "GLRT"}\n')
    row = dict(dataset_label="DS23-0001", recording_id="recording-1",
               recording_format="short_window_iq_recording",
               raw_authority_digest="sha256:raw", tracking_inputs=[dict(
                   path=str(payload), sha256="sha256:" + module.sha(payload))])
    module.write(tmp_path / "sample.json", dict(selected=[row]))
    return row, payload


def test_fast_export_is_manifest_bound_and_replay_verified(tmp_path):
    row, payload = fixture(tmp_path)
    result = module.export(tmp_path, row["dataset_label"])
    assert result["status"] == "exported"
    assert (tmp_path / row["dataset_label"] / "tracking.json").read_bytes() == payload.read_bytes()
    assert result == module.export(tmp_path, row["dataset_label"])
    (tmp_path / row["dataset_label"] / "tracking.json").write_text("changed")
    with pytest.raises(ValueError, match="export changed"):
        module.export(tmp_path, row["dataset_label"])


def test_missing_input_remains_in_cohort_and_authority_change_is_rejected(tmp_path):
    row, _ = fixture(tmp_path)
    row["tracking_inputs"] = []
    module.write(tmp_path / "sample.json", dict(selected=[row]))
    result = module.export(tmp_path, row["dataset_label"])
    assert result["status"] == "input_unavailable"
    assert module.validate_export(tmp_path, row["dataset_label"])["status"] == "input_unavailable"
    row["raw_authority_digest"] = "sha256:changed"
    module.write(tmp_path / "sample.json", dict(selected=[row]))
    with pytest.raises(ValueError, match="membership changed"):
        module.validate_export(tmp_path, row["dataset_label"])


def test_corrupt_frozen_source_is_not_exported(tmp_path):
    row, payload = fixture(tmp_path)
    payload.write_text("modified")
    result = module.export(tmp_path, row["dataset_label"])
    assert result["status"] == "input_unavailable"
    assert "authority changed" in result["reason"]
    assert not (tmp_path / row["dataset_label"] / "tracking.json").exists()


def test_only_unique_sealed_case_names_are_accepted(tmp_path):
    row, _ = fixture(tmp_path)
    with pytest.raises(ValueError, match="unique sealed"):
        module.member(tmp_path, "../DS23-0001")
    module.write(tmp_path / "sample.json", dict(selected=[row, row]))
    with pytest.raises(ValueError, match="unique sealed"):
        module.member(tmp_path, row["dataset_label"])
