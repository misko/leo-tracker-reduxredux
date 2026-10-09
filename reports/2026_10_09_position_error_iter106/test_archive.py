"""Synthetic terminal corpus; never archive the live experiment."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent


def module(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


archiver, unpacker = module("archive_results"), module("unpack_results")


def fixture(root):
    labels = [f"synthetic-{i}" for i in range(148)]
    plan = dict(labels=labels, members=[dict(member=dict(inventory_label=k)) for k in labels])
    (root / "protocol.json").write_text(json.dumps(plan))
    digest = hashlib.sha256((root / "protocol.json").read_bytes()).hexdigest()
    (root / "results").mkdir()
    for binding in plan["members"]:
        member = binding["member"]
        (root / "results" / f"{member['inventory_label']}.json").write_text(
            json.dumps(
                dict(
                    member=member,
                    status="failed",
                    error="synthetic input failure",
                    protocol_sha256=digest,
                )
            )
        )
    claims = root / "controller-claims"
    claims.mkdir()
    (claims / f"{labels[0]}.json").write_text(
        json.dumps(dict(label=labels[0], protocol_sha256=digest))
    )
    (claims / f"{labels[0]}.exit.json").write_text(
        json.dumps(dict(returncode=0, protocol_sha256=digest))
    )
    return plan


def test_determinism_restore_and_preservation(tmp_path):
    fixture(tmp_path)
    first = archiver.archive(tmp_path)
    assert first == archiver.archive(tmp_path)
    assert first["terminal_statuses"] == {"failed": 148} and first["attempt_statuses"] == {}
    assert "parts" not in first
    destination = tmp_path / "restored"
    assert unpacker.restore(destination, tmp_path) == 150
    assert unpacker.restore(destination, tmp_path) == 150
    (destination / "results/synthetic-0.json").write_text("different")
    with pytest.raises(AssertionError, match="Existing file differs"):
        unpacker.restore(destination, tmp_path)


def test_incomplete_and_live_controller_rejected(tmp_path):
    fixture(tmp_path)
    terminal = tmp_path / "results/synthetic-0.json"
    terminal.unlink()
    with pytest.raises(FileNotFoundError):
        archiver.archive(tmp_path)
    assert not (tmp_path / "results-receipts.tar.gz").exists()


def test_chunked_restore_and_symlink_rejection(tmp_path, monkeypatch):
    fixture(tmp_path)
    monkeypatch.setattr(archiver, "CHUNK_THRESHOLD", 1)
    monkeypatch.setattr(archiver, "CHUNK_SIZE", 1000)
    manifest = archiver.archive(tmp_path)
    assert manifest["parts"]
    (tmp_path / "results-receipts.tar.gz").unlink()
    target = tmp_path / "restored"
    assert unpacker.restore(target, tmp_path) == 150
    other = tmp_path / "link"
    other.symlink_to(target, target_is_directory=True)
    with pytest.raises(AssertionError):
        unpacker.restore(other, tmp_path)


def test_stale_protocol_rejected(tmp_path):
    fixture(tmp_path)
    path = tmp_path / "results/synthetic-0.json"
    row = json.loads(path.read_text())
    row["protocol_sha256"] = "stale"
    path.write_text(json.dumps(row))
    with pytest.raises(AssertionError):
        archiver.archive(tmp_path)


def test_raw_failed_attempt_count_is_not_qualified(tmp_path):
    fixture(tmp_path)
    path = tmp_path / "results/synthetic-0.json"
    row = json.loads(path.read_text())
    row.update(status="complete", raw={})
    folder = tmp_path / "attempts/synthetic-0"
    folder.mkdir(parents=True)
    for width in ("125", "100"):
        row["raw"][width] = {}
        for arm in ("fitted-c", "zero-c"):
            attempt = dict(
                protocol_sha256=row["protocol_sha256"],
                member=row["member"],
                status="complete",
                fit=dict(converged=True),
            )
            if width == "100" and arm == "zero-c":
                attempt = dict(attempt, status="failed", error="timeout")
                del attempt["fit"]
            row["raw"][width][arm] = attempt
            (folder / f"sigma{width}-{arm}.json").write_text(json.dumps(attempt))
    path.write_text(json.dumps(row))
    manifest = archiver.archive(tmp_path)
    assert manifest["attempt_statuses"] == dict(complete=3, qualified=3, failed=1)


def test_active_claim_prevents_archiving(tmp_path):
    fixture(tmp_path)
    (tmp_path / "controller-claims/synthetic-0.exit.json").unlink()
    with pytest.raises(AssertionError, match="Controller still active"):
        archiver.archive(tmp_path)
    assert not (tmp_path / "results-receipts.tar.gz").exists()
