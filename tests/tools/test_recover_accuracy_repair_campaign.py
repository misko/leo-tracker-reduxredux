"""Audited interruption recovery never reruns or rewrites finished science."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import recover_accuracy_repair_campaign as recovery


def setup(tmp_path):
    output = tmp_path / "results"
    destination = output / "DS26-0001-r0" / "baseline"
    destination.mkdir(parents=True)
    request = dict(job=dict(output_root=str(destination)))
    original = dict(status="started", role="baseline", request_sha256="request",
                    before=dict(utc="2026-11-17T17:50:00Z"))
    path = destination.parent / "baseline-execution.json"

    def write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    write(path, original)
    write(destination / "experimental-request.json", request)
    (destination / "worker.log").write_text("partial scientific progress\n")
    manifest = dict(output=str(output), roles=["baseline"],
                    schedule=[dict(case="DS26-0001", repetition=0)])
    api = SimpleNamespace(
        bulk_output=Path, host=lambda: dict(utc="recovered"), write=write,
        worker_request=lambda *args: request, validate_record=lambda *args: None,
        ev=SimpleNamespace(read=lambda p: json.loads(Path(p).read_text()),
                           digest=lambda value: "request", file_digest=lambda p: "hash"))
    return api, manifest, path, original, destination


def test_recovery_preserves_interrupted_attempt_and_never_rewrites_a_finished_outcome(tmp_path):
    api, manifest, path, original, destination = setup(tmp_path)
    recovery_root = tmp_path / "recovery"
    changed = recovery.recover_interrupted(api, manifest, recovery_root,
                                           reason="external user-service disruption",
                                           stopped_utc="2026-11-17T17:57:51Z")
    assert changed == [str(path)]
    record = api.ev.read(path)
    assert record["status"] == "failed"
    assert record["process"]["wall_seconds"] == 471
    assert record["process"]["cpu_seconds"] is None
    assert not record["process"]["cpu_complete"]
    assert not record["interruption"]["inference_rerun"]
    evidence = api.ev.read(record["interruption"]["evidence_path"])
    assert evidence["original_record"] == original
    assert str(destination / "worker.log") in evidence["partial_artifacts"]
    before = path.read_bytes()
    assert not recovery.recover_interrupted(api, manifest, recovery_root, reason="resume")
    assert path.read_bytes() == before


def test_recovery_refuses_a_live_worker_or_possible_completed_evidence(tmp_path, monkeypatch):
    api, manifest, path, original, destination = setup(tmp_path)
    monkeypatch.setattr(recovery, "active_workers", lambda path: [123])
    with pytest.raises(RuntimeError, match="still running"):
        recovery.recover_interrupted(api, manifest, tmp_path / "recovery", reason="resume")
    monkeypatch.setattr(recovery, "active_workers", lambda path: [])
    (destination / "worker-result.json").write_text("possible science")
    with pytest.raises(RuntimeError, match="requires inspection"):
        recovery.recover_interrupted(api, manifest, tmp_path / "recovery", reason="resume")
    assert api.ev.read(path) == original


@pytest.mark.parametrize("status", ["complete", "failed", "timed_out", "missing"])
def test_recovery_preserves_every_finished_status_byte_for_byte(tmp_path, status):
    api, manifest, path, original, _ = setup(tmp_path)
    api.write(path, dict(original, status=status))
    before = path.read_bytes()
    assert not recovery.recover_interrupted(api, manifest, tmp_path / "recovery", reason="resume")
    assert path.read_bytes() == before
