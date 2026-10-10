import json

import pytest
from archive_inputs import digest
from archive_parity import create, prepare_files


def test_archive_gates_all_members_and_preserves_failures_no_overwrite(tmp_path):
    members = [dict(label=f"DS16-{i:03}", membership={}) for i in range(193)]
    path = tmp_path / "parity-protocol.json"
    path.write_text(json.dumps(dict(members=members, sources={}, inputs={})))
    directory = tmp_path / "parity-results"
    directory.mkdir()
    with pytest.raises(FileNotFoundError):
        prepare_files(tmp_path, tmp_path)
    protocol_sha = digest(path.read_bytes())
    for m in members:
        value = dict(label=m["label"], protocol_sha256=protocol_sha)
        (directory / (m["label"] + ".claim.json")).write_text(json.dumps(value))
        (directory / (m["label"] + ".json")).write_text(
            json.dumps(
                dict(
                    value,
                    status="failed",
                    error="synthetic retained",
                    optimizer_calls=0,
                    endpoint_evaluations=0,
                    elapsed_s=0,
                )
            )
        )
    manifest = create(tmp_path, tmp_path)
    assert len(manifest["files"]) == 386
    assert (directory / "DS16-000.json").exists()
    with pytest.raises(FileExistsError):
        create(tmp_path, tmp_path)
