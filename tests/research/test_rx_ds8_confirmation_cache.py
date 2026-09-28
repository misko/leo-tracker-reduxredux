import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.rx_ds8_confirmation_cache import canonical, digest, package


@dataclass
class Probe:
    visit_index: int
    probe_index: int
    probe_start_ms: int
    receiver_id: int
    channel: int = 1
    edge: str = "lower"
    valid_start_counter: int = 100
    actual_rf_hz: float = 10_960_000_000.0


class TrackingInput:
    __module__ = "leo.contracts.scanner_tracking"

    def __init__(self, sid, input_hash, analysis_hash, probes):
        self.session_id = sid
        self.input_manifest_sha256 = input_hash
        self.analysis_manifest_sha256 = analysis_hash
        self.sample_rate_hz = 2_500_000
        self.qualified = True
        self.probes = probes


class Store:
    def __init__(self, values):
        self.values = values

    def load(self, sid):
        return self.values[sid]


class Captures:
    def __init__(self, rows):
        self.rows = rows

    def inspect(self, sid):
        row = self.rows[sid]
        events = [SimpleNamespace(visit_index=index) for index in row["visits"]]
        return SimpleNamespace(
            manifest_sha256=row["manifest_sha256"],
            manifest=SimpleNamespace(receipt=SimpleNamespace(events=events)),
        )


def fixture(tmp_path: Path):
    selected, captures, tracking = [], [], {}
    pose_dir = tmp_path / "poses"
    pose_dir.mkdir()
    for number in range(4):
        sid = f"session-{number}"
        input_hash, analysis_hash = f"input-{number}", f"analysis-{number}"
        authority = {
            "revision": "pose-v1",
            "valid_from_utc_ns": 0,
            "valid_until_utc_ns": 10_000,
        }
        pose = {
            "schema_version": 1,
            "session_id": sid,
            "manifest_sha256": input_hash,
            "capture_start_earliest_utc_ns": 100,
            "capture_end_utc_ns": 200,
            "pose_authority": authority,
            "pose_authority_digest": digest(canonical(authority)),
        }
        pose["binding_digest"] = digest(canonical(pose))
        pose_payload = canonical(pose)
        (pose_dir / f"{sid}.json").write_bytes(pose_payload)
        selected.append(
            {
                "session_id": sid,
                "sample_rate_hz": 2_500_000,
                "capture_start_utc_ns": 100,
                "capture_end_utc_ns": 200,
                "input_manifest_sha256": input_hash,
                "analysis_manifest_sha256": analysis_hash,
                "pose_revision": "pose-v1",
                "pose_binding_digest": pose["binding_digest"],
                "tracking_contract": "leo.contracts.scanner_tracking.TrackingInput",
                "probes": 2,
            }
        )
        captures.append(
            {
                "session_id": sid,
                "manifest_sha256": input_hash,
                "sample_rate_hz": 2_500_000,
                "capture_start_utc_ns": 100,
                "capture_end_utc_ns": 200,
                "terminal_state": "completed",
                "terminal_error_code": 0,
                "utc_qualified": True,
                "receiver_ids": [0, 1],
                "visits": 1,
                "pose_file_sha256": digest(pose_payload),
            }
        )
        tracking[sid] = TrackingInput(
            sid, input_hash, analysis_hash, [Probe(1, 0, 0, 0), Probe(1, 0, 0, 1)]
        )
    return (
        {"schema": "rx-ds8-confirmation-readiness/v1", "selected": selected},
        {"captures": captures},
        pose_dir,
        Store(tracking),
        Captures({row["session_id"]: {**row, "visits": [1]} for row in captures}),
    )


def test_packages_exclusive_ready_inventory_without_outcomes(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "tools.rx_ds8_confirmation_cache.pickle.dumps",
        lambda value, protocol: f"{value.session_id}:{protocol}".encode(),
    )
    readiness, ds8, poses, tracking, captures = fixture(tmp_path)
    output = tmp_path / "output"
    receipt = package(readiness, ds8, poses, output, tracking, captures)
    inventory = json.loads((output / "inventory.json").read_text())
    assert receipt["candidate_or_outcome_fields_inspected"] is False
    assert len(inventory) == 4
    assert all(row["ready"] and row["split"] == "evaluation" for row in inventory)
    assert all(Path(row["cache_file"]).is_file() for row in inventory)
    with pytest.raises(FileExistsError):
        package(readiness, ds8, poses, output, tracking, captures)


def test_rejects_corrupt_analysis_binding_before_creating_output(tmp_path):
    readiness, ds8, poses, tracking, captures = fixture(tmp_path)
    readiness["selected"][0]["analysis_manifest_sha256"] = "corrupt"
    output = tmp_path / "output"
    with pytest.raises(ValueError, match="analysis_manifest_sha256 mismatch"):
        package(readiness, ds8, poses, output, tracking, captures)
    assert not output.exists()


def test_rejects_unpaired_probe_without_inspecting_candidates(tmp_path):
    readiness, ds8, poses, tracking, captures = fixture(tmp_path)
    tracking.values["session-0"].probes.pop()
    readiness["selected"][0]["probes"] = 1
    output = tmp_path / "output"
    with pytest.raises(ValueError, match="receiver pair"):
        package(readiness, ds8, poses, output, tracking, captures)
    assert not output.exists()


def test_rejects_duplicate_probe_identity_with_different_start(tmp_path):
    readiness, ds8, poses, tracking, captures = fixture(tmp_path)
    tracking.values["session-0"].probes.append(Probe(1, 0, 120, 0))
    readiness["selected"][0]["probes"] = 3
    output = tmp_path / "output"
    with pytest.raises(ValueError, match="duplicate probes"):
        package(readiness, ds8, poses, output, tracking, captures)
    assert not output.exists()


def test_rejects_readiness_bound_to_another_ds8_payload(tmp_path):
    readiness, ds8, poses, tracking, captures = fixture(tmp_path)
    readiness["source_sha256"] = {"ds8_manifest": "expected"}
    output = tmp_path / "output"
    with pytest.raises(ValueError, match="payload hash mismatch"):
        package(
            readiness,
            ds8,
            poses,
            output,
            tracking,
            captures,
            {"ds8_manifest": "sha256:actual"},
        )
    assert not output.exists()
