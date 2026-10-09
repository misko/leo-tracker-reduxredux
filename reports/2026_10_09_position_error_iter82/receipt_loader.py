"""Join immutable original and input-only retry receipts with explicit provenance."""

import hashlib
import json


def merged_result(binding, original_digest, original_dir, retry_dir):
    member = binding["member"]
    label = member["inventory_label"]
    path = original_dir / "results" / f"{label}.json"
    if not path.exists():
        return dict(status="pending")
    row = json.loads(path.read_text())
    assert row["protocol_sha256"] == original_digest
    assert row["member"] == member
    provenance = dict(original=str(path), original_status=row["status"],
                      original_error=row.get("error"), retry=None)
    retry_path = retry_dir / "results" / f"{label}.json"
    if retry_path.exists():
        assert row["status"] == "failed"
        assert "cannot import name 'digest' from 'freeze'" in row["error"]
        protocol = retry_dir / "protocol.json"
        plan = json.loads(protocol.read_text())
        expected = next(b for b in plan["members"] if b["member"]["inventory_label"] == label)
        assert expected == binding
        row = json.loads(retry_path.read_text())
        assert row["member"] == member
        assert row["protocol_sha256"] == hashlib.sha256(protocol.read_bytes()).hexdigest()
        provenance["retry"] = str(retry_path)
    row["provenance"] = provenance
    return row
