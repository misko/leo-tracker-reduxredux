import json
from pathlib import Path

import audit_metadata as audit


def test_literal_identity_matches_and_scope(tmp_path, monkeypatch):
    here = tmp_path / "own"
    (here / "local").mkdir(parents=True)
    capture = dict(
        session_id="scan-fw-test",
        uncompressed_sha256="sha256:iq",
        recording_manifest_sha256="sha256:input",
    )
    (here / "local/manifest.json").write_text(json.dumps(dict(captures=[capture])))
    root = tmp_path / "reports"
    root.mkdir()
    for name, token in [
        ("session.json", capture["session_id"]),
        ("input.md", capture["recording_manifest_sha256"]),
        ("iq.txt", capture["uncompressed_sha256"]),
        ("excluded.bin", capture["session_id"]),
    ]:
        (root / name).write_text(token)
    with (root / "large.json").open("wb") as stream:
        stream.write(capture["session_id"].encode())
        stream.truncate(64 * 1024**2 + 1)
    monkeypatch.setattr(audit, "HERE", here)
    monkeypatch.setattr(audit, "ROOTS", [root])
    receipt = audit.scan()
    assert {Path(m["path"]).name for m in receipt["matches"]} == {
        "session.json",
        "input.md",
        "iq.txt",
    }
    assert all(m["sessions"] == ["scan-fw-test"] for m in receipt["matches"])
    assert receipt["files_scanned"] == 3 and not receipt["access_errors"]
    assert len(receipt["skipped_large_files"]) == 1
