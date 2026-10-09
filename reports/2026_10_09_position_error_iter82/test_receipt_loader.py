import hashlib
import json

import pytest
from receipt_loader import merged_result


def setup_receipts(tmp_path):
    old, retry = tmp_path / "old", tmp_path / "retry"
    for directory in (old, retry):
        (directory / "results").mkdir(parents=True)
    binding = dict(member=dict(inventory_label="DS17-001", dataset="DS17"))
    original = dict(member=binding["member"], protocol_sha256="original", status="failed",
                    error="ImportError: cannot import name 'digest' from 'freeze'")
    (old / "results/DS17-001.json").write_text(json.dumps(original))
    (retry / "protocol.json").write_text(json.dumps(dict(members=[binding])))
    return old, retry, binding


def test_failure_remains_until_retry_exists(tmp_path):
    old, retry, binding = setup_receipts(tmp_path)
    row = merged_result(binding, "original", old, retry)
    assert row["status"] == "failed"
    assert row["provenance"]["retry"] is None


def test_retry_preserves_failure_and_checks_digest(tmp_path):
    old, retry, binding = setup_receipts(tmp_path)
    row = dict(status="complete", member=binding["member"], protocol_sha256="wrong")
    path = retry / "results/DS17-001.json"
    path.write_text(json.dumps(row))
    with pytest.raises(AssertionError):
        merged_result(binding, "original", old, retry)
    row["protocol_sha256"] = hashlib.sha256((retry / "protocol.json").read_bytes()).hexdigest()
    path.write_text(json.dumps(row))
    merged = merged_result(binding, "original", old, retry)
    assert merged["status"] == "complete"
    assert merged["provenance"]["original_status"] == "failed"
    assert "ImportError" in merged["provenance"]["original_error"]


def test_cannot_replace_successful_original(tmp_path):
    old, retry, binding = setup_receipts(tmp_path)
    path = old / "results/DS17-001.json"
    row = json.loads(path.read_text())
    row["status"] = "complete"
    path.write_text(json.dumps(row))
    (retry / "results/DS17-001.json").write_text("{}")
    with pytest.raises(AssertionError):
        merged_result(binding, "original", old, retry)
