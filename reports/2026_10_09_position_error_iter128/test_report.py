import hashlib
import json

import pytest
from report import summarize


def test_pending_has_no_fabricated_changes(tmp_path):
    (tmp_path / "protocol.json").write_text("{}")
    summary, _ = summarize({"members": [{"label": "a", "expected_observations": 2}]}, tmp_path)
    assert not summary["coverage_complete"]
    assert summary["successful_rows_only_changes"]["newton"] is None


def test_failure_coverage_and_changed_row_digest(tmp_path):
    protocol = tmp_path / "protocol.json"
    protocol.write_text("{}")
    metadata = tmp_path / "metadata.json"
    metadata.write_text(json.dumps({"window_ids": ["a", "b"]}))
    md = hashlib.sha256(metadata.read_bytes()).hexdigest()
    binding = {
        "label": "m",
        "expected_observations": 2,
        "metadata_path": str(metadata),
        "metadata_sha256": md,
        "sample_rate_hz": 2500000,
    }
    directory = tmp_path / "results/m"
    directory.mkdir(parents=True)
    rows = [
        {
            "window_id": "a",
            "status": "complete",
            "result": {
                "changes": {
                    k: {"circular_hz": 100, "wrap_count": 1} for k in ("logparabola", "newton")
                }
            },
        },
        {"window_id": "b", "status": "budget-exhausted"},
    ]
    row_path = directory / "rows.jsonl"
    row_path.write_text("\n".join(json.dumps(row) for row in rows))
    receipt = {
        "protocol_sha256": hashlib.sha256(protocol.read_bytes()).hexdigest(),
        "metadata_sha256": md,
        "rows_sha256": hashlib.sha256(row_path.read_bytes()).hexdigest(),
        "counts": {"complete": 1, "budget-exhausted": 1},
        "status": "complete-with-failures",
    }
    (directory / "result.json").write_text(json.dumps(receipt))
    summary, _ = summarize({"members": [binding]}, tmp_path)
    assert summary["coverage_complete"]
    assert len(summary["failures"]) == 1
    assert summary["successful_rows_only_changes"]["newton"]["count"] == 1
    row_path.write_text("changed")
    with pytest.raises(ValueError, match="rows digest"):
        summarize({"members": [binding]}, tmp_path)
