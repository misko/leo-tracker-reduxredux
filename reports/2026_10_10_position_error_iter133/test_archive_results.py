import json
import runpy
from pathlib import Path

import pytest

api = runpy.run_path(str(Path(__file__).with_name("archive_results.py")))


def fixture(folder):
    folder.mkdir()
    (folder / "results").mkdir()
    members = [dict(label=f"LABEL-{i:03d}") for i in range(12)]
    (folder / "protocol.json").write_text(json.dumps(dict(members=members, sources={}, inputs={})))
    digest = api["digest"](folder / "protocol.json")
    for member in members:
        identity = dict(label=member["label"], protocol_sha256=digest)
        (folder / "results" / (member["label"] + ".claim.json")).write_text(json.dumps(identity))
        result = dict(identity, status="failed" if member["label"].endswith("011") else "complete")
        (folder / "results" / (member["label"] + ".json")).write_text(json.dumps(result))
    return folder


def test_deterministic_archive_preserves_all_originals_and_failed_member(tmp_path):
    first, second = [fixture(tmp_path / name) for name in ("one", "two")]
    before = {path.name: path.read_bytes() for path in (first / "results").glob("*.json")}
    result = api["create"](first, tmp_path)
    again = api["create"](second, tmp_path)
    assert result["sha256"] == again["sha256"] and len(result["files"]) == 24
    assert before == {path.name: path.read_bytes() for path in (first / "results").glob("*.json")}
    with pytest.raises(FileExistsError):
        api["create"](first, tmp_path)


def test_missing_or_foreign_receipt_prevents_archive(tmp_path):
    folder = fixture(tmp_path / "one")
    path = folder / "results/LABEL-011.json"
    path.unlink()
    with pytest.raises(FileNotFoundError):
        api["create"](folder, tmp_path)
    assert not (folder / "results.tar.gz").exists()
    path.write_text(json.dumps(dict(label="foreign", protocol_sha256="bad", status="complete")))
    with pytest.raises(ValueError, match="Foreign"):
        api["create"](folder, tmp_path)
