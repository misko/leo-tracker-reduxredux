import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from leo.cli import algo07v5
from leo.operations.localization_v3_job import JobInterrupted
from leo.operations.localization_v5_job import make_request
from tests.analysis.test_localization_v4_native import native_manifest as native_manifest
from tests.operations.test_localization_v3_job import request_fixture
from tests.operations.test_localization_v5_job import saved


def invoke(action, request, manifest, directory):
    path = directory.parent / (directory.name + "-request.json")
    path.write_text(json.dumps(request))
    native = directory.parent / (directory.name + "-manifest.json")
    native.write_text(json.dumps(manifest))
    environment = dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1",
                       MKL_NUM_THREADS="1")
    return subprocess.run(
        [sys.executable, "-m", "leo.cli.algo07v5", action,
         "--request", str(path), "--work-dir", str(directory),
         "--native-manifest", str(native), "--timeout", "15"],
        env=environment, capture_output=True, text=True, timeout=25,
    )


def test_real_supervisor_runs_v5_worker_and_keeps_failure_receipts(native_manifest, tmp_path):
    request = make_request(request_fixture(tmp_path), native_manifest)
    attempt = tmp_path / "attempt"
    process = invoke("run", request, native_manifest, attempt)
    assert process.returncode == 1, process.stderr
    supervisor = json.loads((attempt / "supervisor.json").read_bytes())
    launch = json.loads((attempt / "launch.json").read_bytes())
    assert "leo.cli.algo07v5" in launch["command"]
    assert "--native-manifest" in launch["command"]
    assert supervisor["status"] == "exited"
    assert supervisor["worker"]["status"] == "failed"
    assert "absent-native" in supervisor["worker"]["error"]


def test_real_resume_publishes_saved_v5_without_native_artifacts(native_manifest, tmp_path):
    request = make_request(request_fixture(tmp_path), native_manifest)
    manifest = deepcopy(native_manifest)
    for name in ("source", "wrapper", "binary"):
        manifest[name] = str(tmp_path / ("absent-" + name))
    manifest["provider"]["path"] = str(tmp_path / "absent-provider")
    request["backend_manifest"] = manifest
    saved(request)
    attempt = tmp_path / "resume"
    process = invoke("resume", request, manifest, attempt)
    assert process.returncode == 0, process.stderr + process.stdout
    supervisor = json.loads((attempt / "supervisor.json").read_bytes())
    assert supervisor["worker"]["resumed"] is True
    assert supervisor["worker"]["publication"]["implementation_model"] == "algo07v5-native-v1"
    assert not (attempt / "native-receipts").exists()


def test_manifest_mismatch_rejected_before_worker_launch(native_manifest, tmp_path):
    request = make_request(request_fixture(tmp_path), native_manifest)
    manifest = dict(native_manifest, compiler_version="changed")
    attempt = tmp_path / "attempt"
    process = invoke("run", request, manifest, attempt)
    assert process.returncode == 1
    assert "binding" in process.stderr
    assert not attempt.exists()


@pytest.mark.parametrize('field,value', [
    ('initial_control_policy', 'other'), ('algorithm', 'algo07v4-native-v1'),
    ('schema_version', 2),
])
def test_wrong_policy_or_version_rejected_before_worker_launch(
    native_manifest, tmp_path, field, value
):
    request = make_request(request_fixture(tmp_path), native_manifest)
    request[field] = value
    attempt = tmp_path / 'attempt'
    process = invoke('run', request, native_manifest, attempt)
    assert process.returncode == 1
    assert 'Complete native ALGO07v5 request required' in process.stderr
    assert not attempt.exists()


def test_help_identifies_v5():
    process = subprocess.run([sys.executable, '-m', 'leo.cli.algo07v5', '--help'],
                             capture_output=True, text=True, timeout=10)
    assert process.returncode == 0
    assert 'ALGO07v5' in process.stdout


@pytest.mark.parametrize("interrupted", [False, True])
def test_worker_records_failures_and_interrupts(tmp_path, monkeypatch, interrupted):
    from leo.operations import localization_v5_job

    def fail(*args, **kwargs):
        raise JobInterrupted("cancelled") if interrupted else ValueError("bad backend")

    monkeypatch.setattr(localization_v5_job, "execute", fail)
    path = tmp_path / "request.json"
    path.write_text("{}")
    outcome = tmp_path / "outcome.json"
    args = SimpleNamespace(request=path, outcome=outcome,
                           native_manifest=Path("/unused"), resume_only=False)
    assert algo07v5.worker(args) == (130 if interrupted else 1)
    expected = "interrupted" if interrupted else "failed"
    assert json.loads(outcome.read_bytes())["status"] == expected


def test_worker_serializes_control_integrity_abort_as_failed(tmp_path, monkeypatch):
    from leo.analysis.localization_v5.control_reuse import ControlReuseFailure
    from leo.operations import localization_v5_job

    def fail(*args, **kwargs):
        raise ControlReuseFailure('changed bound identity')

    monkeypatch.setattr(localization_v5_job, 'execute', fail)
    path = tmp_path / 'request.json'
    path.write_text('{}')
    outcome = tmp_path / 'outcome.json'
    args = SimpleNamespace(request=path, outcome=outcome,
                           native_manifest=Path('/unused'), resume_only=False)
    assert algo07v5.worker(args) == 1
    result = json.loads(outcome.read_bytes())
    assert result == dict(status='failed',
                         error='ControlReuseFailure: changed bound identity')
