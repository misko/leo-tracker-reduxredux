import json

import pytest
from archive_results import API, create


def fixture(folder):
    folder.mkdir()
    (folder / "results").mkdir()
    members = [dict(label=f"member-{i}") for i in range(12)]
    (folder / "protocol.json").write_text(json.dumps(dict(members=members, sources={}, inputs={})))
    digest = API["digest"](folder / "protocol.json")
    for member in members:
        identity = dict(label=member["label"], protocol_sha256=digest)
        (folder / "results" / (member["label"] + ".claim.json")).write_text(json.dumps(identity))
        (folder / "results" / (member["label"] + ".json")).write_text(
            json.dumps(
                dict(identity, status="failed" if member["label"] == "member-11" else "complete")
            )
        )
    return folder


def test_deterministic_archive_preserves_failed_member_and_originals(tmp_path):
    first, second = [fixture(tmp_path / name) for name in ("one", "two")]
    before = {p.name: p.read_bytes() for p in (first / "results").glob("*.json")}
    a, b = create(first, tmp_path), create(second, tmp_path)
    assert a["sha256"] == b["sha256"] and len(a["files"]) == 24
    assert before == {p.name: p.read_bytes() for p in (first / "results").glob("*.json")}


def test_missing_receipt_prevents_archive_creation(tmp_path):
    folder = fixture(tmp_path / "one")
    (folder / "results/member-11.json").unlink()
    with pytest.raises(FileNotFoundError):
        create(folder, tmp_path)
    assert not (folder / "results.tar.gz").exists()
