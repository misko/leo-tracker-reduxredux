from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from leo.analysis.research.doppler_dataset_policy import load_doppler_dataset_policy
from tools import experiment_retrospective_satellite_nuisance as tool

ROOT = Path(__file__).parents[2]
PROTOCOL = ROOT / "config" / "analysis" / "retrospective-satellite-nuisance-protocol-v1.json"


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _document() -> dict[str, object]:
    value = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_post_outcome_durability_amendment_seals_original_bytes() -> None:
    amendment_bytes = tool.TLE_DURABILITY_AMENDMENT.read_bytes()
    amendment = json.loads(amendment_bytes)
    assert "sha256:" + hashlib.sha256(amendment_bytes).hexdigest() == (
        tool.TLE_DURABILITY_AMENDMENT_SHA256
    )
    original = amendment["original_protocol"]
    assert _sha256(ROOT / original["path"]) == original["sha256"]
    historical = amendment["historical_archive_index"]
    assert historical["role"] == "provenance_only"
    assert historical["current_or_historical_index_bytes_required_for_replay"] is False
    sealed = amendment["sealed_outcome_preservation"]
    assert sealed["scientific_change"] is False
    assert sealed["iq_read_or_experiment_rerun_authorized"] is False
    for label in ("report", "evidence", "artifact_manifest"):
        assert _sha256(ROOT / sealed[f"{label}_path"]) == sealed[f"{label}_sha256"]


def test_protocol_uses_only_open_authorized_post_fix_captures() -> None:
    document = _document()
    authority = document["authority"]
    assert isinstance(authority, dict)
    policy_path = ROOT / str(authority["dataset_policy_path"])
    assert _sha256(policy_path) == authority["dataset_policy_sha256"]
    policy = load_doppler_dataset_policy(policy_path)

    required = tuple(authority["required_capture_ids"])
    allowed = set()
    for role_name in authority["allowed_policy_roles"]:
        allowed.update(policy.role(str(role_name)).capture_ids)
    assert set(required) <= allowed
    assert set(required).isdisjoint(policy.role("holdout_foundation").capture_ids)
    assert all(
        policy.capture(capture_id).provenance_status.endswith("_opened") for capture_id in required
    )


def test_protocol_binds_existing_measurement_bytes() -> None:
    document = _document()
    inputs = document["measurement_inputs"]
    assert isinstance(inputs, dict)
    for key in ("multi_radio_frame_ledger", "long_150802_ledger"):
        binding = inputs[key]
        assert isinstance(binding, dict)
        path = ROOT / str(binding["path"])
        assert path.is_file()
        assert _sha256(path) == binding["sha256"]


def test_every_tle_is_digest_bound_and_strictly_pre_measurement() -> None:
    document = _document()
    tle_inputs = document["tle_inputs"]
    assert isinstance(tle_inputs, dict)
    snapshots = tle_inputs["snapshots"]
    assert isinstance(snapshots, dict)
    for binding in snapshots.values():
        assert isinstance(binding, dict)
        path = Path(str(binding["raw_path"]))
        assert _sha256(path) == binding["raw_sha256"]
        retrieved = datetime.fromisoformat(str(binding["retrieved_at"]).replace("Z", "+00:00"))
        first = datetime.fromtimestamp(int(binding["first_measurement_utc_ns"]) / 1e9, UTC)
        assert retrieved < first

    sensitivity = tle_inputs["source_sensitivity"]
    assert isinstance(sensitivity, dict)
    latest = sensitivity["cap-20260825T150802-473cb5bbcbd6"]
    assert isinstance(latest, dict)
    collected = datetime.fromisoformat(str(latest["collected_at"]).replace("Z", "+00:00"))
    first = datetime.fromtimestamp(int(latest["first_measurement_utc_ns"]) / 1e9, UTC)
    assert collected < first
    reconstructed = tool._latest_causal_tle_text(document)
    assert (
        "sha256:" + hashlib.sha256(reconstructed.encode("ascii")).hexdigest()
        == latest["raw_sha256"]
    )
    amendment = json.loads(tool.TLE_DURABILITY_AMENDMENT.read_text(encoding="utf-8"))
    reconstruction = amendment["latest_causal_tle_reconstruction"]
    assert reconstruction["historical_temporary_raw_path_required_for_replay"] is False
    tool.load_protocol(PROTOCOL)


def test_replay_never_reads_the_mutable_index(monkeypatch: pytest.MonkeyPatch) -> None:
    document = _document()
    mutable_index = Path(str(document["tle_inputs"]["archive_index_path"]))
    original_read_bytes = Path.read_bytes

    def guarded_read_bytes(path: Path) -> bytes:
        if path == mutable_index:
            raise AssertionError("mutable TLE index must not be replay authority")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)
    loaded = tool.load_protocol(PROTOCOL)
    assert loaded["tle_inputs"]["archive_index_path"] == str(mutable_index)


def test_replay_fails_closed_on_raw_tle_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    amendment = json.loads(tool.TLE_DURABILITY_AMENDMENT.read_text(encoding="utf-8"))
    receipt = amendment["frozen_snapshots"]["cap-20260825T065355-ba3e4fb8857b"]
    raw_path = Path(receipt["raw_path"])
    original_read_bytes = Path.read_bytes

    def drifted_read_bytes(path: Path) -> bytes:
        payload = original_read_bytes(path)
        return payload[:-1] + bytes([payload[-1] ^ 1]) if path == raw_path else payload

    monkeypatch.setattr(Path, "read_bytes", drifted_read_bytes)
    with pytest.raises(ValueError, match="raw TLE digest drifted"):
        tool.load_protocol(PROTOCOL)


def test_replay_fails_closed_on_snapshot_metadata_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    amendment = json.loads(tool.TLE_DURABILITY_AMENDMENT.read_text(encoding="utf-8"))
    receipt = amendment["frozen_snapshots"]["cap-20260825T065355-ba3e4fb8857b"]
    metadata_path = Path(receipt["snapshot_metadata_path"])
    original_read_bytes = Path.read_bytes

    def drifted_read_bytes(path: Path) -> bytes:
        payload = original_read_bytes(path)
        return payload.replace(b"05:37:00", b"05:38:00", 1) if path == metadata_path else payload

    monkeypatch.setattr(Path, "read_bytes", drifted_read_bytes)
    with pytest.raises(ValueError, match="snapshot metadata digest drifted"):
        tool.load_protocol(PROTOCOL)


def test_replay_fails_closed_on_cross_bound_timestamp_drift() -> None:
    document = _document()
    amendment = json.loads(tool.TLE_DURABILITY_AMENDMENT.read_text(encoding="utf-8"))
    receipt = amendment["frozen_snapshots"]["cap-20260825T065355-ba3e4fb8857b"]
    receipt["retrieved_at"] = "2026-08-25T05:38:00.001167Z"

    with pytest.raises(ValueError, match="receipt disagrees with protocol"):
        tool._validate_tle_durability_amendment(document, PROTOCOL, amendment)


def test_replay_fails_closed_on_reconstruction_authority_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_read_bytes = Path.read_bytes

    def drifted_read_bytes(path: Path) -> bytes:
        payload = original_read_bytes(path)
        if path == tool.LATEST_TLE_RECONSTRUCTION:
            return payload + b"\n"
        return payload

    monkeypatch.setattr(Path, "read_bytes", drifted_read_bytes)
    with pytest.raises(ValueError, match="latest-causal TLE durability receipt drifted"):
        tool.load_protocol(PROTOCOL)


def test_identity_gates_separate_track_recovery_from_secure_norad() -> None:
    document = _document()
    gates = document["promotion_gates"]
    assert isinstance(gates, dict)
    recovered = gates["recovered_track"]
    candidate = gates["candidate_evidence"]
    secure = gates["secure_norad"]
    assert len(recovered) == 4
    assert any("quadratic" in item for item in candidate)
    assert any("wrong-time" in item for item in candidate)
    assert any("two independent" in item for item in secure)
    assert gates["counting"]["no_promotion_from_in_sample_rms_only"] is True
