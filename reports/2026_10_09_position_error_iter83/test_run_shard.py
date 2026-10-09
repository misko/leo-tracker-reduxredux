import hashlib
import json
import subprocess

import pytest
from run_shard import run


def setup_plan(tmp_path):
    member = dict(inventory_label="TEST")
    (tmp_path / "protocol.json").write_text(json.dumps(
        dict(shards=1, members=[dict(member=member)])
    ))
    (tmp_path / "results").mkdir()
    return dict(member=member, status="complete", protocol_sha256=hashlib.sha256(
        (tmp_path / "protocol.json").read_bytes()).hexdigest())


def test_successful_completion_stops_without_duplicate_invocation(tmp_path):
    result = setup_plan(tmp_path)
    calls = []
    def invoke(args, check):
        assert check
        calls.append(args)
        (tmp_path / "results/TEST.json").write_text(json.dumps(result))
    run(tmp_path, 0, 3, invoke)
    assert len(calls) == 1


def test_fatal_exit_is_not_automatically_retried(tmp_path):
    setup_plan(tmp_path)
    calls = []
    def invoke(args, check):
        calls.append(args)
        raise subprocess.CalledProcessError(2, args)
    with pytest.raises(subprocess.CalledProcessError):
        run(tmp_path, 0, 3, invoke)
    assert len(calls) == 1


def test_incomplete_successes_have_bounded_serial_resumes(tmp_path):
    setup_plan(tmp_path)
    calls = []
    run(tmp_path, 0, 3, lambda args, check: calls.append(args))
    assert len(calls) == 3
