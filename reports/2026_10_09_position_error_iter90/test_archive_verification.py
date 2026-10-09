"""Synthetic archival integrity tests; no recording or position result access."""

import hashlib
import json

import pytest
import verify_archive


def prepare(tmp_path, monkeypatch):
    monkeypatch.setattr(verify_archive, "HERE", tmp_path)
    monkeypatch.setattr(verify_archive, "ROOT", tmp_path)
    members = [
        dict(dataset=d, inventory_label=f"{d}-{i:03d}")
        for d, count in [("DS16", 63), ("DS17", 51), ("DS18", 34)]
        for i in range(1, count + 1)
    ]
    plan = dict(source_sha256={}, members=[dict(member=m) for m in members])
    protocol = json.dumps(plan).encode()
    (tmp_path / "protocol.json").write_bytes(protocol)
    digest = hashlib.sha256(protocol).hexdigest()
    (tmp_path / "results").mkdir()
    for member in members:
        receipt = dict(
            member=member,
            protocol_sha256=digest,
            status="complete",
            objective_checks={arm: dict(delta=0) for arm in ("fitted-c", "zero-c")},
        )
        (tmp_path / "results" / (member["inventory_label"] + ".json")).write_text(
            json.dumps(receipt)
        )


def test_full_archive_roundtrip_and_all_objective_checks(tmp_path, monkeypatch):
    prepare(tmp_path, monkeypatch)
    verify_archive.main()
    receipt = json.loads((tmp_path / "verification.json").read_text())
    assert receipt["members"] == 148
    assert receipt["objectives_checked"] == receipt["exact_zero_objective_deltas"] == 296
    assert len(receipt["archived_receipt_sha256"]) == 148
    assert receipt["archive_bytes"] > 0


def test_missing_receipt_prevents_archive_claim(tmp_path, monkeypatch):
    prepare(tmp_path, monkeypatch)
    (tmp_path / "results/DS18-034.json").unlink()
    with pytest.raises(AssertionError):
        verify_archive.main()
    assert not (tmp_path / "verification.json").exists()


def test_unqualified_endpoint_prevents_archive_claim(tmp_path, monkeypatch):
    prepare(tmp_path, monkeypatch)
    path = tmp_path / "results/DS18-034.json"
    receipt = json.loads(path.read_text())
    receipt["objective_checks"]["fitted-c"]["delta"] = 0.1
    path.write_text(json.dumps(receipt))
    with pytest.raises(AssertionError):
        verify_archive.main()
    assert not (tmp_path / "verification.json").exists()
