import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from run import verify_prerequisites


def test_all193_parity_gates_fail_before_any_fit(tmp_path):
    members = []
    for i in range(193):
        label = f"member-{i:03}"
        path = tmp_path / (label + ".json")
        path.write_text(
            json.dumps(
                dict(
                    label=label,
                    status="complete",
                    protocol_sha256="fixed",
                    endpoint_evaluations=2,
                    reference_error="poison-unused",
                    arms={a: dict(status="complete", delta=0) for a in ("fitted-c", "zero-c")},
                )
            )
        )
        members.append(dict(label=label, parity_receipt=str(path)))
    plan = dict(
        members=members,
        sources={},
        inputs={},
        maximum_fit_calls=772,
        maximum_seconds_per_fit=90,
        maximum_iterations_per_fit=600,
        qualification_threshold=0.001,
        parity_protocol_sha256="fixed",
        arms=["fitted-c", "zero-c"],
        variants=["timestamp", "phase"],
    )
    verify_prerequisites(plan)
    path = Path(members[-1]["parity_receipt"])
    original = json.loads(path.read_text())
    for change in (dict(status="failed"), dict(protocol_sha256="foreign")):
        path.write_text(json.dumps(dict(original, **change)))
        with pytest.raises(ValueError, match="prerequisite"):
            verify_prerequisites(plan)
    path.write_text(json.dumps(original))
    original["arms"]["zero-c"]["status"] = "failed"
    path.write_text(json.dumps(original))
    with pytest.raises(ValueError, match="Arm parity"):
        verify_prerequisites(plan)
    path.unlink()
    with pytest.raises(FileNotFoundError):
        verify_prerequisites(plan)


def test_exact_dependency_import_order_without_recording_calls():
    root = Path(__file__).resolve().parents[2]
    code = """
import runpy,sys,importlib.util
from pathlib import Path
r=Path.cwd()/"reports"
runpy.run_path(str(r/"2026_10_09_position_error_iter106/engine.py"))
for name,path in [("parity137_for140",r/"2026_10_10_position_error_iter137/parity.py"),
("helpers132_for140",r/"2026_10_10_position_error_iter132/audit.py"),
("clean131_for140",r/"2026_10_09_position_error_iter131/inference_loader.py"),
("entry116_for140",r/"2026_10_09_position_error_iter116/entrypoint.py")]:
 if name.startswith("entry"):sys.path.insert(0,str(path.parent))
 spec=importlib.util.spec_from_file_location(name,path)
 value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
print("imports-only-passed")
"""
    env = dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=root, env=env, capture_output=True, text=True, check=True
    )
    assert "imports-only-passed" in result.stdout


def test_controller_stops_on_missing_foreign_or_interrupted_receipt(tmp_path):
    from batch import run_members

    plan = dict(members=[dict(label="one"), dict(label="two")])
    directory = tmp_path / "results"
    directory.mkdir()
    calls = []

    def missing(label):
        calls.append(label)

    with pytest.raises(ValueError, match="without terminal"):
        run_members(plan, "fixed", tmp_path, missing)
    assert calls == ["one"]

    def foreign(label):
        calls.append(label)
        (directory / (label + ".json")).write_text(
            json.dumps(dict(label=label, protocol_sha256="wrong", status="complete"))
        )

    calls.clear()
    with pytest.raises(ValueError, match="Foreign"):
        run_members(plan, "fixed", tmp_path, foreign)
    assert calls == ["one"]
    (directory / "one.json").unlink()
    (directory / "one.claim.json").write_text("{}")
    calls.clear()
    with pytest.raises(ValueError, match="Claim exists"):
        run_members(plan, "fixed", tmp_path, missing)
    assert calls == []
