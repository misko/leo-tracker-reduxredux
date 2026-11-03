"""Cohort authority, immutable source and resource-isolation controls."""

import json
from pathlib import Path

import pytest

import run_algo02_ds23 as runner


def member(case, identity):
    return dict(dataset_label=case, recording_id=identity, recording_format="fast",
        case_id=case, captured_utc_ns=1, tracking_inputs=[],
        raw_recording=dict(identity_sha256="sha256:abc"))


def test_compaction_keeps_unready_members_and_rejects_duplicate_identity():
    rows = runner.compact_members(dict(members=[member("B", "b"), member("A", "a")]))
    assert [row["dataset_label"] for row in rows] == ["A", "B"]
    assert len(rows) == 2 and all(not row["tracking_inputs"] for row in rows)
    with pytest.raises(ValueError, match="recording identities"):
        runner.compact_members(dict(members=[member("A", "a"), member("B", "a")]))


def test_source_closure_follows_function_local_imports(tmp_path):
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools/start.py").write_text("def f():\n    import helper\n")
    (tmp_path / "tools/helper.py").write_text("x = 1\n")
    result = runner.source_closure(["tools/start.py"], root=tmp_path)
    assert set(result) == {"tools/start.py", "tools/helper.py"}


def test_frozen_membership_or_source_changes_are_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    source = tmp_path / "source.py"
    source.write_text("x=1\n")
    runner.write(tmp_path / "sample.json", dict(selected=[]))
    runner.write(tmp_path / "protocol.json", dict(sample_sha256=runner.digest(tmp_path / "sample.json"),
        source_sha256={"source.py": runner.digest(source)}))
    runner.verify_freeze(tmp_path)
    source.write_text("x=2\n")
    with pytest.raises(ValueError, match="source changed"):
        runner.verify_freeze(tmp_path)
    source.write_text("x=1\n")
    runner.write(tmp_path / "sample.json", dict(selected=["unexpected"]))
    with pytest.raises(ValueError, match="membership changed"):
        runner.verify_freeze(tmp_path)


def test_receipt_resume_detects_changed_result(tmp_path):
    directory = tmp_path / "CASE"
    directory.mkdir()
    runner.write(tmp_path / "protocol.json", {})
    result = directory / "algo02_result.json"
    runner.write(result, dict(status="complete"))
    runner.write(directory / "execution_receipt.json", dict(case="CASE", code=0,
        protocol_sha256=runner.digest(tmp_path / "protocol.json"), result_sha256=runner.digest(result)))
    runner.write(result, dict(status="changed"))
    with pytest.raises(ValueError, match="scientific result changed"):
        runner.worker("CASE", tmp_path, {})


def test_child_timeout_is_terminal_and_blas_threads_are_bounded(tmp_path):
    import os
    import sys
    with (tmp_path / "log").open("w") as stream:
        result = runner.bounded_command([sys.executable, "-c", "import time; time.sleep(30)"],
            stream, .05, os.environ.copy())
    assert result == 124
    assert set(runner.THREAD_ENV.values()) == {"1"}
