from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

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


def test_every_tle_is_digest_bound_and_strictly_pre_measurement(tmp_path: Path) -> None:
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

    latest["raw_path"] = str(tmp_path / "deliberately-absent-historical-source.tle")
    durable_protocol = tmp_path / "durable-protocol.json"
    durable_protocol.write_text(json.dumps(document), encoding="utf-8")
    tool.load_protocol(durable_protocol)


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
