import hashlib
import json
from pathlib import Path

HERE = Path(__file__).parents[2] / "reports/2026_09_23_final_test_global_epoch"


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def test_amended_test_preserves_failed_full_view_and_prefix_membership():
    frozen = json.loads((HERE / "freeze.json").read_text())
    amendment = json.loads((HERE / "execution_amendment.json").read_text())
    receipts = json.loads((HERE / "cache_receipts.json").read_text())
    assert amendment["original_freeze"] == digest(HERE / "freeze.json")
    assert amendment["cache_receipts"] == digest(HERE / "cache_receipts.json")
    assert [row["session_id"] for row in receipts["rows"]] == frozen["session_ids"]
    failed = [row for row in receipts["rows"] if "failure" in row]
    assert len(failed) == 1
    assert failed[0]["session_id"] == amendment["failed_session_id"]
    assert frozen["session_ids"].index(failed[0]["session_id"]) + 1 == 48
    assert amendment["successful_fixed_prefixes"] == [1, 6, 16]
    assert amendment["failed_fixed_prefixes"] == [64]


def test_all_seals_and_amended_source_hashes_match():
    amendment = json.loads((HERE / "execution_amendment.json").read_text())
    for name, expected in amendment["amended_sources"].items():
        assert digest(HERE / name) == expected
    for stage in ("baseline", "timing"):
        path = HERE / stage / "inference.json"
        assert (
            hashlib.sha256(path.read_bytes()).hexdigest()
            == path.with_suffix(".sha256").read_text().strip()
        )
    path = HERE / "results.json"
    assert (
        hashlib.sha256(path.read_bytes()).hexdigest()
        == path.with_suffix(".sha256").read_text().strip()
    )
    for filename in ("baseline/inference.json", "timing/inference.json", "results.json"):
        rows = json.loads((HERE / filename).read_text())[
            "arms" if "inference" in filename else "rows"
        ]
        assert len(rows) == 8
        failures = [row for row in rows if "failure" in row]
        assert len(failures) == 2
        assert {row.get("scan_count", row.get("view_scan_count")) for row in failures} == {64}
