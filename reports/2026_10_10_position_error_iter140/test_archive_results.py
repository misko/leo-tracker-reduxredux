import json

import pytest
from archive_results import SAFE, create, prepare_files


def test_full_terminal_gates_and_deterministic_failure_preservation(tmp_path):
    members = [dict(label=f"case-{i:03}") for i in range(193)]
    protocol = tmp_path / "protocol.json"
    protocol.write_text(json.dumps(dict(members=members, sources={}, inputs={})))
    directory = tmp_path / "results"
    directory.mkdir()
    with pytest.raises(FileNotFoundError):
        prepare_files(tmp_path, tmp_path)
    digest = SAFE.digest(protocol.read_bytes())
    for member in members:
        label = member["label"]
        identity = dict(label=label, protocol_sha256=digest)
        (directory / (label + ".claim.json")).write_text(json.dumps(identity))
        (directory / (label + ".json")).write_text(
            json.dumps(
                dict(
                    identity,
                    status="attempt-failed",
                    attempts={"phase": {"zero-c": {"error": "retained"}}},
                )
            )
        )
    wrong = directory / "case-192.claim.json"
    wrong.write_text(json.dumps(dict(label="foreign", protocol_sha256=digest)))
    with pytest.raises(ValueError, match="Foreign"):
        prepare_files(tmp_path, tmp_path)
    wrong.write_text(json.dumps(dict(label="case-192", protocol_sha256=digest)))
    archive = create(tmp_path, tmp_path)
    assert len(archive["files"]) == 386
    assert json.loads((directory / "case-192.json").read_text())["status"] == "attempt-failed"
    with pytest.raises(FileExistsError):
        create(tmp_path, tmp_path)
