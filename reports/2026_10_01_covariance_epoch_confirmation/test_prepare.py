import hashlib
import importlib.util
import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("confirmation_prepare", HERE / "prepare.py")
PREPARE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = PREPARE
SPEC.loader.exec_module(PREPARE)


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def test_publication_parser_requires_published_digest_and_uses_realtime_ns(tmp_path):
    path = tmp_path / "journal.jsonl"
    messages = [
        {
            "__REALTIME_TIMESTAMP": "123",
            "MESSAGE": json.dumps({
                "event": "tle_collection",
                "providers": [
                    {"provider": "a", "digest": "d1", "status": "published"},
                    {"provider": "b", "digest": "d2", "status": "failed"},
                ],
            }),
        },
        {"__REALTIME_TIMESTAMP": "124", "MESSAGE": json.dumps({"event": "other"})},
        {"__REALTIME_TIMESTAMP": "bad", "MESSAGE": "{}"},
    ]
    path.write_text("\n".join(json.dumps(row) for row in messages) + "\n")
    assert PREPARE.publication_times(path) == {("a", "d1"): [123_000]}


def test_inventory_is_exactly_selection_bound_and_generated_evidence_is_consistent():
    selection_path = HERE / "selection.json"
    selection = json.loads(selection_path.read_text())
    inventory = json.loads((HERE / "inventory.json").read_text())
    expected = {
        row["unit_id"]: (dataset, row)
        for dataset, rows in selection["selected"].items()
        for row in rows
    }
    actual = {row["unit_id"]: row for row in inventory["rows"]}
    assert len(actual) == len(inventory["rows"]) == 32
    assert actual.keys() == expected.keys()
    assert inventory["selection_sha256"] == _sha256(selection_path)
    for unit_id, row in actual.items():
        dataset, selected = expected[unit_id]
        assert row["session_id"] == selected["session_id"]
        assert row["dataset"] == dataset
        assert row["status"] in {"ready", "needs_export"}
        evidence_path = HERE / "evidence" / f"{unit_id}.json"
        if not evidence_path.exists():
            assert row["status"] == "needs_export"
            continue
        evidence = json.loads(evidence_path.read_text())
        assert evidence["session_id"] == selected["session_id"]
        assert evidence["manifest_sha256"] == selected["manifest_sha256"]
        source = Path(evidence["source"]["path"])
        assert source.is_file()
        assert evidence["source"]["sha256"] == _sha256(source)
        source_document = json.loads(source.read_text())
        assert source_document["session_id"] == selected["session_id"]
        assert isinstance(source_document["start_utc_ns"], int)
        assert source_document["tracks"]
        if row["status"] == "ready":
            assert row["source"] == str(source)
            assert row["sha256"] == evidence["source"]["sha256"]
