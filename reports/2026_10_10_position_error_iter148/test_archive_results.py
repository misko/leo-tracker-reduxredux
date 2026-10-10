import json

import pytest
from archive_results import SAFE, create, prepare

from leo.contracts.digests import canonical_digest


def fixture(root):
    plan = dict(
        source_sha256={},
        input_sha256={},
        evaluation_source_sha256={},
        branches={b: [{}, {}, {}] for b in ("native", "zero")},
    )
    digest = canonical_digest(plan)
    (root / "protocol.json").write_text(json.dumps(plan))
    for branch in ("native", "zero"):
        folder = root / "results" / branch
        folder.mkdir(parents=True)
        (folder / "result.json").write_text(
            json.dumps(dict(branch=branch, status="failed", protocol_sha256=digest))
        )
    (root / "SUMMARY.json").write_text(json.dumps(dict(both_terminal=True, protocol_sha256=digest)))
    return digest


def test_archive_failed_receipts_deterministic_restore_and_no_overwrite(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    fixture(first)
    fixture(second)
    a = create(first, first)
    b = create(second, second)
    assert a["archive_sha256"] == b["archive_sha256"]
    destination = tmp_path / "restored"
    SAFE.restore(first / "results-summary.tar.gz", a, destination)
    assert json.loads((destination / "results/zero/result.json").read_text())["status"] == "failed"
    (destination / "SUMMARY.json").write_text("changed")
    with pytest.raises(ValueError, match="refuse overwrite"):
        SAFE.restore(first / "results-summary.tar.gz", a, destination)
    with pytest.raises(FileExistsError):
        create(first, first)


def test_missing_or_foreign_terminal_blocks_archive(tmp_path):
    fixture(tmp_path)
    terminal = tmp_path / "results/zero/result.json"
    value = json.loads(terminal.read_text())
    value["protocol_sha256"] = "foreign"
    terminal.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="Foreign"):
        prepare(tmp_path, tmp_path)
    terminal.unlink()
    with pytest.raises(FileNotFoundError):
        prepare(tmp_path, tmp_path)
    assert not (tmp_path / "results-summary.tar.gz").exists()
