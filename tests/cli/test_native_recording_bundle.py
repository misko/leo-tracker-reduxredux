"""Manifest admission uses public-port fixtures, without firmware dependencies."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys

import pytest

from leo.operations.native_recording_bundle import load_native_bundle, review_native_bundle
from tests.cli.test_native_journal_recording import binding_for, recording


def encoded(value):
    return (json.dumps(value, sort_keys=True) + "\n").encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def bundle(tmp_path):
    root = tmp_path / "bundle"
    root.mkdir()
    value = recording()
    # Opaque raw producer evidence. Its internal interpretation belongs to the
    # producer; the application checks exact bytes and the public ports.
    payloads = {
        "journal.glrj": b"GLRJ1\n" + bytes(1994),
        "owner-receipt.json": b"{}\n",
        "coarse-protocol.json": b"{}\n",
        "coarse-summary.json": b"{}\n",
        "coarse-final-snapshot.txt": b"retained producer snapshot\n",
    }
    value["journal_sha256"] = digest(payloads["journal.glrj"])
    payloads["recording.json"] = encoded(value)
    source = binding_for(value, digest(payloads["recording.json"]))
    for key, name in [
        ("owner_receipt_sha256", "owner-receipt.json"),
        ("collector_protocol_sha256", "coarse-protocol.json"),
        ("collector_summary_sha256", "coarse-summary.json"),
        ("collector_final_snapshot_sha256", "coarse-final-snapshot.txt"),
    ]:
        source[key] = digest(payloads[name])
    payloads["source-binding.json"] = encoded(source)
    keys = (
        "serial",
        "boot_id",
        "fit_sha256",
        "visit",
        "epoch",
        "episode_index",
        "runtime_result",
        "owner_status",
        "head_count",
        "supported_count",
        "evidence_mode",
    )
    manifest = {key: source[key] for key in keys}
    manifest.update(
        schema="starlink-glrt-native-recording-bundle/v1",
        publication_status="complete",
        coarse_iq={
            "sha256": source["coarse_iq_sha256"],
            "bytes": source["coarse_iq_bytes"],
            "embedded": False,
        },
        artifacts={
            name: {"sha256": digest(raw), "bytes": len(raw)} for name, raw in payloads.items()
        },
        acquisition_verified=False,
        original_native_iq_verified=False,
        physical_precision_qualified=False,
    )
    for name, raw in payloads.items():
        (root / name).write_bytes(raw)
    path = root / "manifest.json"
    path.write_bytes(encoded(manifest))
    return path, manifest


def test_bundle_cli_preserves_bound_recording_and_failed_owner(tmp_path):
    path, manifest = bundle(tmp_path)
    sha = digest(path.read_bytes())
    selected = load_native_bundle(path, expected_sha256=sha)
    assert selected.manifest.epoch == selected.recording.epoch == selected.source_binding.epoch == 3
    assert selected.manifest.runtime_result == -5 and selected.manifest.owner_status == "failed"
    output = tmp_path / "review"
    command = [
        sys.executable,
        "-m",
        "leo.cli.native_recording_bundle",
        "--manifest",
        str(path),
        "--sha256",
        sha,
        "--output",
        str(output),
    ]
    result = subprocess.run(command, check=True, text=True, capture_output=True)
    summary = json.loads(result.stdout)
    assert summary["runtime_result"] == -5 and summary["owner_status"] == "failed"
    assert summary["radio_boot_source_bound"] and not summary["physical_precision_qualified"]
    assert (
        summary["source_binding"]["recording_export_sha256"]
        == manifest["artifacts"]["recording.json"]["sha256"]
    )
    assert (output / "measurements.csv").exists()


@pytest.mark.parametrize(
    "corruption",
    [
        "missing",
        "payload",
        "bytes",
        "manifest_hash",
        "partial",
        "traversal",
        "symlink",
        "identity",
        "outcome",
        "source_hash",
        "coarse_iq",
        "journal_length",
        "duplicate",
    ],
)
def test_bad_or_incomplete_publication_creates_no_review(tmp_path, corruption):
    path, manifest = bundle(tmp_path)
    expected = None
    if corruption == "missing":
        (path.parent / "owner-receipt.json").unlink()
    elif corruption == "payload":
        (path.parent / "owner-receipt.json").write_bytes(b"[]\n")
    elif corruption == "bytes":
        manifest["artifacts"]["recording.json"]["bytes"] += 1
    elif corruption == "manifest_hash":
        expected = "0" * 64
    elif corruption == "partial":
        manifest["publication_status"] = "started"
    elif corruption == "traversal":
        manifest["artifacts"]["../outside"] = manifest["artifacts"].pop("owner-receipt.json")
    elif corruption == "symlink":
        target = path.parent / "owner-receipt.json"
        outside = tmp_path / "outside"
        outside.write_bytes(target.read_bytes())
        target.unlink()
        target.symlink_to(outside)
    elif corruption == "identity":
        manifest["boot_id"] = "00000000-0000-0000-0000-000000000000"
    elif corruption == "outcome":
        manifest["runtime_result"] = 0
    elif corruption == "source_hash":
        raw = b'{"other":true}\n'
        (path.parent / "owner-receipt.json").write_bytes(raw)
        manifest["artifacts"]["owner-receipt.json"] = {"bytes": len(raw), "sha256": digest(raw)}
    elif corruption == "coarse_iq":
        manifest["coarse_iq"]["bytes"] += 4
    elif corruption == "journal_length":
        raw = (path.parent / "journal.glrj").read_bytes() + b"\n"
        (path.parent / "journal.glrj").write_bytes(raw)
        manifest["artifacts"]["journal.glrj"] = {"bytes": len(raw), "sha256": digest(raw)}
    path.write_bytes(encoded(manifest))
    if corruption == "duplicate":
        path.write_bytes(path.read_bytes().replace(b'"epoch": 3', b'"epoch": 3, "epoch": 3'))
    expected = expected or digest(path.read_bytes())
    with pytest.raises((ValueError, OSError)):
        review_native_bundle(path, tmp_path / "review", expected_sha256=expected)
    assert not (tmp_path / "review").exists()


def test_directory_without_final_manifest_is_not_a_publication(tmp_path):
    root = tmp_path / "incomplete"
    root.mkdir()
    (root / "journal.glrj").write_bytes(b"GLRJ1\n")
    with pytest.raises(FileNotFoundError):
        load_native_bundle(root / "manifest.json", expected_sha256="0" * 64)
