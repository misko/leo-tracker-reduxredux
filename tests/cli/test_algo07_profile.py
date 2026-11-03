"""Runtime profiling must preserve frozen scientific evidence and failure states."""

import argparse
import json
from pathlib import Path

import pytest

from leo.cli.algo07_profile import destination, digest, freeze, run, verify


def frozen(tmp_path):
    evidence = tmp_path / "input.json"
    evidence.write_text('{"scientific_result": 3}\n')
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({"files": [{"path": evidence.name, "sha256": digest(evidence)}]}))
    manifest = tmp_path / "reference.json"
    freeze(spec, manifest)
    return evidence, manifest


def test_freeze_verifies_expected_bytes_and_detects_later_changes(tmp_path):
    evidence, manifest = frozen(tmp_path)
    assert verify(manifest) == dict(verified=True, files=1, failed=[])
    evidence.write_text('{"scientific_result": 4}\n')
    assert verify(manifest)["failed"] == [str(evidence)]
    with pytest.raises(ValueError, match="hash mismatch"):
        freeze(tmp_path / "spec.json", tmp_path / "other.json")


def test_reference_is_not_overwritten_and_qnap_is_readonly(tmp_path):
    _, manifest = frozen(tmp_path)
    with pytest.raises(FileExistsError):
        freeze(tmp_path / "spec.json", manifest)
    with pytest.raises(ValueError, match="read-only"):
        destination(Path("/mnt/qnap01/benchmark/attempt"))
    link = tmp_path / "linked"
    link.symlink_to("/mnt/qnap01")
    with pytest.raises(ValueError, match="read-only"):
        destination(link / "attempt")


def arguments(tmp_path, script, manifest, **changes):
    values = dict(
        manifest=manifest,
        output=tmp_path / "run",
        script=script,
        stage="test",
        timeout=5,
        no_cprofile=False,
        arguments=[],
    )
    values.update(changes)
    return argparse.Namespace(**values)


def test_profile_records_success_without_claiming_scientific_parity(tmp_path):
    _, manifest = frozen(tmp_path)
    script = tmp_path / "worker.py"
    script.write_text("print(sum(i * i for i in range(1000)))\n")
    result = run(arguments(tmp_path, script, manifest))
    assert result["successful_execution"] is True
    assert result["scientific_parity_checked"] is False
    assert result["wall_seconds"] > 0
    assert (tmp_path / "run/profile.pstats").stat().st_size > 0


def test_mutating_reference_is_failure_even_with_zero_worker_exit(tmp_path):
    evidence, manifest = frozen(tmp_path)
    script = tmp_path / "worker.py"
    script.write_text(f'from pathlib import Path\nPath({str(evidence)!r}).write_text("changed")\n')
    result = run(arguments(tmp_path, script, manifest))
    assert result["exit_code"] == 0
    assert result["successful_execution"] is False
    assert result["reference_after"]["verified"] is False


def test_timeout_is_recorded_as_incomplete(tmp_path):
    _, manifest = frozen(tmp_path)
    script = tmp_path / "worker.py"
    script.write_text("import time\ntime.sleep(10)\n")
    result = run(arguments(tmp_path, script, manifest, timeout=0.1))
    assert result["timed_out"] is True
    assert result["successful_execution"] is False
    assert result["reference_after"]["verified"] is True
