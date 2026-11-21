import hashlib
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.pipeline_eval.qualification import original_v5
from tools.pipeline_eval.scoring import ARMS, ROLES, validate_result


def digest(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def test_ds30_original_requires_the_same_frozen_roof_tile_and_native_input(tmp_path):
    case = dict(panel="DS30", regions=[dict(center=original_v5.v5.ROOF_CENTER)])
    assert "Native detector input" in original_v5.run(case, tmp_path, "baseline")["reason"]
    case["regions"] = [dict(center=(0, 0))]
    assert "25 km roof tile" in original_v5.run(case, tmp_path, "baseline")["reason"]


@pytest.mark.parametrize("role", ROLES)
def test_role_binding_preserves_scientific_inputs_without_mutating_baseline(role, tmp_path):
    case_id, session, native = "DS29-0082", "session-id", "sha256:native"
    policies = {name: f"policy-{name}" for name in ROLES}
    source, manifest = {"sha256": "sha256:source"}, {"binary_sha256": "sha256:backend"}
    identity = dict(
        case=case_id,
        repetition=0,
        role="baseline",
        source=source["sha256"],
        native=manifest,
        input=native,
    )
    baseline = dict(
        role="baseline",
        policy=policies["baseline"],
        source=source,
        native_manifest=manifest,
        causal_snapshots={"earlier.tle": "sha256:tle"},
        job=dict(
            native_input={"sha256": native, "path": "/previous/native.json"},
            identity={"run_id": "experiment-" + digest(identity)[7:47], "session_id": session},
            track_config={"sha256": "sha256:config"},
            evaluation_reference=None,
        ),
    )
    original = digest(baseline)
    args = (role, policies, tmp_path, "/new/native.json", case_id, session, native, digest)
    rebound = original_v5._bind(baseline, *args)
    assert digest(baseline) == original
    assert (rebound["role"], rebound["policy"]) == (role, policies[role])
    assert rebound["job"]["identity"]["run_id"] == (
        "experiment-" + digest(dict(identity, role=role))[7:47]
    )
    assert rebound["job"]["output_root"] == str(tmp_path)
    assert rebound["job"]["native_input"] == {"sha256": native, "path": "/new/native.json"}
    assert rebound["job"]["track_config"] == baseline["job"]["track_config"]
    assert rebound["causal_snapshots"] == baseline["causal_snapshots"]
    assert rebound["native_manifest"] == baseline["native_manifest"]
    assert rebound["job"]["evaluation_reference"] is None

    with pytest.raises(ValueError, match="case"):
        original_v5._bind(
            baseline,
            role,
            policies,
            tmp_path,
            "/new/native.json",
            "DS29-0000",
            session,
            native,
            digest,
        )
    baseline["job"]["evaluation_reference"] = {"latitude_deg": 37.8, "longitude_deg": -122.5}
    with pytest.raises(ValueError, match="Evaluation reference"):
        original_v5._bind(baseline, *args)


@pytest.fixture
def local_runtime(tmp_path, monkeypatch):
    bulk = tmp_path / "bulk"
    scratch = bulk / "leo-dev"
    scratch.mkdir(parents=True)
    monkeypatch.setattr(original_v5, "BULK", bulk)
    monkeypatch.setattr(original_v5, "CACHE", tmp_path / "scientific-cache")
    monkeypatch.setattr(original_v5.v5, "RUNNER", tmp_path)
    monkeypatch.setattr(original_v5.v5, "SOURCE", tmp_path)
    monkeypatch.setattr(original_v5.v5, "PYTHON", Path(__file__))
    monkeypatch.delenv("LEO_PIPELINE_EVAL_V5_SCRATCH", raising=False)
    native, request = tmp_path / "native.json", tmp_path / "baseline.json"
    native.touch()
    request.touch()
    case = dict(
        id="DS29-0082",
        panel="DS29",
        regions=[{"center": [37.906, -122.545]}],
        native_path=str(native),
        request_path=str(request),
    )
    return case, scratch


def test_local_replay_returns_published_arms_and_preserves_validated_evidence(
    tmp_path,
    monkeypatch,
    local_runtime,
):
    case, scratch = local_runtime
    rms = {"c0": 97.0, "fitted_c": 96.0}
    role = "selective-gap"
    blob = b"scientific evidence"
    sha = "sha256:" + hashlib.sha256(blob).hexdigest()
    worker = dict(
        role=role,
        policy="policy-id",
        request_sha256="request-id",
        source_sha256="source-id",
        native_manifest_sha256="backend-id",
        artifact={"sha256": sha},
        stage_timings=[{"stage": "png_rendering", "seconds": 2.5}],
        arms={
            arm: dict(
                endpoint_latlon=[38.0, -122.0],
                residual_rms_hz=rms[arm],
                associated_points=7,
                frequency_score=12.0,
            )
            for arm in ARMS
        },
    )

    def launch(command, *, env, **kwargs):
        assert command[0:2] == ["taskset", "-c"]
        assert env["OPENBLAS_NUM_THREADS"] == "1"
        directory = Path(command[7])
        assert directory.parent == scratch
        assert command[8] == role
        (directory / original_v5.EVIDENCE).write_bytes(blob)
        (directory / "worker-result.json").write_text(json.dumps(worker))
        for name in ("experimental-request.json", "validated-archive.json"):
            (directory / name).write_text("{}")
        return SimpleNamespace(returncode=0, wait=lambda **_: None, poll=lambda: 0)

    monkeypatch.setattr(original_v5.subprocess, "Popen", launch)
    directory = tmp_path / "out"
    result = original_v5.run(case, directory, role)
    validate_result(result)
    assert result["status"] == "ok"
    for arm in ARMS:
        assert result["arms"][arm] == {"latlon": [38.0, -122.0], "rf_rms_hz": rms[arm]}
        assert result["metrics"][f"{arm}_frequency_score"] == 12.0
    assert result["metrics"]["stages"] == ["png_rendering"]
    assert result["evidence"] == {"file": original_v5.EVIDENCE, "sha256": sha}
    assert (directory / original_v5.EVIDENCE).read_bytes() == blob
    assert list(scratch.iterdir()) == []


@pytest.mark.parametrize(
    ("reason", "status"),
    [
        ("ValueError: Complete science and every PNG required: no_active_curvature", "withheld"),
        ("ValueError: Frozen original v5 worker binding changed: evaluate_algo07.py", "failed"),
    ],
)
def test_worker_failures_keep_the_reason_without_publishing_a_fix(
    tmp_path,
    monkeypatch,
    local_runtime,
    reason,
    status,
):
    case, bulk = local_runtime

    def launch(*_, stdout, **kwargs):
        stdout.write((reason + "\n").encode())
        stdout.flush()
        return SimpleNamespace(returncode=1, wait=lambda **_: None, poll=lambda: 1)

    monkeypatch.setattr(original_v5.subprocess, "Popen", launch)
    result = original_v5.run(case, bulk / "out", "baseline")
    validate_result(result)
    assert result["status"] == status
    assert result["reason"] == reason
    assert result["arms"] == {arm: {"latlon": None} for arm in ARMS}
    assert "evidence" not in result


def test_deadline_terminates_the_worker_and_reports_timeout(monkeypatch, local_runtime):
    case, bulk = local_runtime
    stopped = []

    def wait(**kwargs):
        if "timeout" in kwargs:
            raise subprocess.TimeoutExpired("v5", kwargs["timeout"])

    process = SimpleNamespace(pid=1234, wait=wait, poll=lambda: None)
    monkeypatch.setattr(original_v5.subprocess, "Popen", lambda *_, **__: process)
    monkeypatch.setattr(original_v5.v5, "_stop_process_tree", stopped.append)
    result = original_v5.run(case, bulk / "out", "omitted-tracks")
    validate_result(result)
    assert result["status"] == "timed_out"
    assert stopped == [process.pid]
    assert "evidence" not in result
