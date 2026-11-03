import hashlib
import importlib.util
import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("sacramento_prepare", HERE / "prepare.py")
PREPARE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = PREPARE
SPEC.loader.exec_module(PREPARE)


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def test_quantile_selection_is_unique_monotone_and_has_exact_panel_size():
    selection = json.loads((HERE / "selection.json").read_text())
    assert selection["counts"] == {"DS9": 11, "DS10": 11, "DS11": 10}
    all_sessions = []
    for dataset, count in selection["counts"].items():
        rows = selection["selected"][dataset]
        indices = [row["selection_index"] for row in rows]
        assert len(rows) == count
        assert indices == PREPARE.selected_indices(
            selection["authorities"][dataset]["count"], count
        )
        assert indices == sorted(set(indices))
        assert [row["capture_start_utc_ns"] for row in rows] == sorted(
            row["capture_start_utc_ns"] for row in rows
        )
        all_sessions.extend(row["session_id"] for row in rows)
    assert len(all_sessions) == len(set(all_sessions)) == 32


def test_publication_parser_requires_published_digest_and_uses_realtime_ns(tmp_path):
    path = tmp_path / "journal.jsonl"
    messages = [
        {
            "__REALTIME_TIMESTAMP": "123",
            "MESSAGE": json.dumps(
                {
                    "event": "tle_collection",
                    "providers": [
                        {"provider": "a", "digest": "d1", "status": "published"},
                        {"provider": "b", "digest": "d2", "status": "failed"},
                    ],
                }
            ),
        },
        {"__REALTIME_TIMESTAMP": "124", "MESSAGE": json.dumps({"event": "other"})},
        {"__REALTIME_TIMESTAMP": "bad", "MESSAGE": "{}"},
    ]
    path.write_text("\n".join(json.dumps(row) for row in messages) + "\n")
    assert PREPARE.publication_times(path) == {("a", "d1"): [123_000]}


def test_every_selection_has_one_source_bound_inventory_row():
    selection = json.loads((HERE / "selection.json").read_text())
    inventory = json.loads((HERE / "inventory.json").read_text())
    expected = {
        row["unit_id"]: row
        for rows in selection["selected"].values()
        for row in rows
    }
    actual = {row["unit_id"]: row for row in inventory["rows"]}
    assert len(actual) == len(inventory["rows"]) == 32
    assert actual.keys() == expected.keys()
    assert inventory["selection_sha256"] == _sha256(HERE / "selection.json")
    for unit_id, row in actual.items():
        selected = expected[unit_id]
        assert row["session_id"] == selected["session_id"]
        assert row["dataset"] == unit_id.split("-", 1)[0]
        assert row["status"] in {"ready", "needs_export"}
        evidence_path = HERE / "evidence" / f"{unit_id}.json"
        if evidence_path.exists():
            evidence = json.loads(evidence_path.read_text())
            assert evidence["session_id"] == selected["session_id"]
            assert evidence["manifest_sha256"] == selected["manifest_sha256"]
            source = Path(evidence["source"]["path"])
            assert source.is_file()
            assert evidence["source"]["sha256"] == _sha256(source)
            if row["status"] == "ready":
                assert row["source"] == str(source)
                assert row["sha256"] == evidence["source"]["sha256"]
            source_document = json.loads(source.read_text())
            assert source_document["session_id"] == selected["session_id"]
            assert isinstance(source_document["start_utc_ns"], int)
            assert source_document["tracks"]
            assert all(
                len(track["times_s"]) == len(track["measured_hz"])
                and len(track["times_s"]) >= 3
                for track in source_document["tracks"]
            )
            preparation_receipt = HERE / "preparation" / f"{unit_id}.json"
            if preparation_receipt.exists():
                prepared = json.loads(preparation_receipt.read_text())
                assert prepared["unit"] == unit_id
                assert prepared["returncode"] == 0
        else:
            assert row["status"] == "needs_export"


def test_authority_hashes_and_capture_metadata_remain_bound():
    selection = json.loads((HERE / "selection.json").read_text())
    for dataset, authority in selection["authorities"].items():
        path = Path(authority["path"])
        assert authority["sha256"] == _sha256(path)
        captures = json.loads(path.read_text())["captures"]
        by_session = {row["session_id"]: row for row in captures}
        for selected in selection["selected"][dataset]:
            source = by_session[selected["session_id"]]
            for field in (
                "manifest_sha256",
                "capture_start_utc_ns",
                "capture_start_earliest_utc_ns",
                "sample_rate_hz",
            ):
                assert selected[field] == source[field]
