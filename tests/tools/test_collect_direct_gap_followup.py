"""The final collector refuses incomplete evidence and cannot start inference."""

import ast
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import collect_direct_gap_followup as collector


def sha(path):
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def fixture(tmp_path, monkeypatch):
    name, case = "ds26-fresh-v2", "DS26-0263"
    monkeypatch.setattr(collector, "EXPECTED", {name: (case, [("baseline", "candidate")])})
    path = tmp_path / "plans" / (name + ".json")
    output = tmp_path / "output"
    role = dict(
        source={"root": "/source"},
        evaluator="/evaluator",
        backend_manifest={"native": "same"},
        initial=None,
    )
    manifest = dict(
        schedule=[dict(case=case, repetition=0, order=["baseline", "candidate"])],
        timeout=2400,
        fast_flags={"--recovery-target-limit": "0"},
        archive_root=str(tmp_path / "archive"),
        output=str(output),
        roles=dict(baseline=role, candidate=dict(role, direct_gap={"id": "direct-timing-gap-v1"})),
    )
    write(path, manifest)
    runner_path = tmp_path / "runner.py"
    runner_path.write_text("frozen runner")
    helper_path = tmp_path / "helper.py"
    helper_path.write_text("frozen archive helper")
    receipt = dict(
        path=str(path),
        file_sha256=sha(path),
        digest=digest(manifest),
        schedule=manifest["schedule"],
        archive=manifest["archive_root"],
        staging=manifest["output"],
    )
    scope = dict(
        pair_count=8,
        worker_count=16,
        launch_order=[name],
        cpu_affinity="21",
        blas_threads=1,
        runner=dict(path=str(runner_path), sha256=sha(runner_path)),
        helper=dict(path=str(helper_path), sha256=sha(helper_path)),
        manifest={name: receipt},
    )
    scope_path = tmp_path / "scope-receipt-v2.json"
    write(scope_path, scope)
    write(
        output / "terminal.json",
        dict(
            status="complete",
            failures=[],
            paired_coverage_complete=True,
            candidate_coverage_complete=True,
        ),
    )
    write(tmp_path / "audit-ds26-0263" / "pair-audit.json", {})
    runner = SimpleNamespace(
        sha=sha,
        read=lambda p: json.loads(Path(p).read_text()),
        digest=digest,
        FAST_FLAGS=manifest["fast_flags"],
        check_bindings=lambda m: None,
    )
    return path, scope_path, runner_path, runner


def test_preflight_rejects_changed_scope(tmp_path, monkeypatch):
    _, scope_path, runner_path, runner = fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="scope receipt changed"):
        collector.preflight(tmp_path, "sha256:wrong", runner_path, runner)
    assert scope_path.exists()


def test_preflight_rejects_changed_manifest(tmp_path, monkeypatch):
    manifest_path, scope_path, runner_path, runner = fixture(tmp_path, monkeypatch)
    manifest_path.write_text(manifest_path.read_text() + "\n")
    with pytest.raises(ValueError, match="Frozen manifest changed"):
        collector.preflight(tmp_path, sha(scope_path), runner_path, runner)


def test_preflight_rejects_missing_worker_report(tmp_path, monkeypatch):
    _, scope_path, runner_path, runner = fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="Missing worker report"):
        collector.preflight(tmp_path, sha(scope_path), runner_path, runner)


def test_collector_has_no_inference_launch_path():
    tree = ast.parse(Path(collector.__file__).read_text())
    forbidden = {"run", "refresh", "Popen", "check_call", "check_output"}
    assert not any(
        isinstance(node, (ast.Import, ast.ImportFrom))
        and any(alias.name == "subprocess" for alias in node.names)
        for node in ast.walk(tree)
    )
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in forbidden
        for node in ast.walk(tree)
    )
