"""Component tests for the DS7 research-evaluation orchestrator.

The tests use the real frozen DS7 metadata authority but only tiny synthetic
JSON exports and synthetic adapter positions.  They never open IQ and their
coordinates are not scientific results.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import ds7_eval, ds7_position_controls


@pytest.mark.parametrize(
    "command", [["/usr/bin/sudo", "python"], ["env", "sudo", "python"], ["setsid", "python"]]
)
def test_privilege_or_session_launcher_rejected_before_execution(command, tmp_path):
    with pytest.raises(ValueError, match="retain runner UID"):
        ds7_eval.execute(command, tmp_path / "request", tmp_path / "response", 1, tmp_path / "log")
    assert not (tmp_path / "log").exists()


def test_timeout_reaps_same_uid_child(tmp_path, monkeypatch):
    processes = []
    original_popen = subprocess.Popen

    def record_process(*args, **kwargs):
        process = original_popen(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(subprocess, "Popen", record_process)
    script = tmp_path / "sleep.py"
    script.write_text("import time\ntime.sleep(30)\n")
    with pytest.raises(subprocess.TimeoutExpired):
        ds7_eval.execute(
            [sys.executable, str(script)],
            tmp_path / "request",
            tmp_path / "response",
            0.05,
            tmp_path / "log",
        )
    assert len(processes) == 1
    assert processes[0].poll() is not None and processes[0].returncode < 0


@pytest.fixture(scope="module")
def ds7_authority() -> tuple[dict, dict]:
    return ds7_eval.load_dataset()


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _prepared(tmp_path: Path, suite: str = "smoke") -> tuple[Path, Path]:
    root = tmp_path / "prepared"
    ds7_eval.prepare(ds7_eval.DEFAULT_DATASET, root, suite)
    return root / "plan.json", root / "inputs.template.json"


def _freeze(
    tmp_path: Path,
    *,
    suite: str = "smoke",
    ready_count: int = 1,
) -> tuple[Path, Path, Path]:
    plan_path, template_path = _prepared(tmp_path, suite)
    index = ds7_eval.read_json(template_path)
    for position, row in enumerate(index["captures"]):
        if position < ready_count:
            artifact = tmp_path / f"synthetic-scan-{position:03}.json"
            _write_json(
                artifact,
                {
                    "schema": "synthetic-ds7-test-export/v1",
                    "session_id": row["session_id"],
                    "observations_hz": [100.0 + position, 101.0 + position],
                },
            )
            row.update(
                state="ready",
                reason=None,
                artifacts=[{"kind": "scan_estimate", "path": str(artifact)}],
            )
    index["reference_audit"] = "reference_excluded"
    index_path = tmp_path / "input-index.json"
    _write_json(index_path, index)
    inputs_path = tmp_path / "inputs.json"
    ds7_eval.freeze_inputs(plan_path, index_path, inputs_path)
    return plan_path, inputs_path, index_path


def _adapter(tmp_path: Path, body: str) -> tuple[Path, Path]:
    script = tmp_path / "synthetic_adapter.py"
    script.write_text(
        "import argparse, json, pathlib, sys, time\n"
        "p=argparse.ArgumentParser()\n"
        "p.add_argument('--request', required=True)\n"
        "p.add_argument('--response', required=True)\n"
        "a=p.parse_args()\n"
        "request_path=pathlib.Path(a.request)\n"
        "response_path=pathlib.Path(a.response)\n"
        "request=json.loads(request_path.read_text())\n" + body
    )
    arm = tmp_path / "arm.json"
    _write_json(
        arm,
        {
            "schema": "ds7-arm/v1",
            "status": "ready",
            "model_id": "synthetic-test-model",
            "command": [sys.executable, str(script)],
            "config": {"purpose": "orchestration-test-only"},
            "code_paths": [str(script)],
        },
    )
    return arm, script


def _valid_body(*, boundary: bool = False) -> str:
    response = {
        "schema": "ds7-response/v1",
        "status": "ok",
        "estimate": {"latitude_deg": 0.25, "longitude_deg": -0.5},
        "converged": True,
        "boundary_hit": boundary,
        "horizontal_radius_95_m": 2000.0,
    }
    return (
        f"response={response!r}\n"
        "response['unit_id']=request['unit']['unit_id']\n"
        "response_path.write_text(json.dumps(response))\n"
    )


def _run(
    tmp_path: Path,
    body: str,
    *,
    suite: str = "smoke",
    ready_count: int = 1,
    selected_units: list[str] | None = None,
    unit_seconds: float = 2.0,
) -> Path:
    plan, inputs, _ = _freeze(tmp_path, suite=suite, ready_count=ready_count)
    arm, _ = _adapter(tmp_path, body)
    output = tmp_path / "run"
    ds7_eval.run(
        plan,
        inputs,
        arm,
        output,
        max_seconds=max(3.0, unit_seconds),
        unit_seconds=unit_seconds,
        selected_units=selected_units,
    )
    return output


def test_real_plans_are_deterministic_and_truth_free(
    ds7_authority: tuple[dict, dict],
) -> None:
    manifest, units = ds7_authority
    standard = ds7_eval.make_plan(manifest, units, "standard")
    repeated = ds7_eval.make_plan(manifest, units, "standard")
    budgets = ds7_eval.make_plan(manifest, units, "budgets")

    assert standard == repeated
    assert len(standard["units"]) == 88 + 11 + 1
    assert len(budgets["units"]) == 88 + 3 * 11 + 1
    assert set(standard["captures"][0]) == set(ds7_eval.CAPTURE_FIELDS)
    assert standard["units"][-1]["session_ids"] == units["full_dataset"]
    ds7_eval.reject_reference_fields(standard["captures"])
    serialized = ds7_eval.canonical(standard)
    assert b"latitude_deg" not in serialized
    assert b"longitude_deg" not in serialized
    assert b"pose_authority" not in serialized


def test_dataset_tamper_is_rejected(tmp_path: Path) -> None:
    copied = tmp_path / "ds7"
    shutil.copytree(ds7_eval.DEFAULT_DATASET, copied)
    with (copied / "README.md").open("a") as stream:
        stream.write("tampered\n")

    with pytest.raises(ValueError, match="Changed: README.md"):
        ds7_eval.load_dataset(copied)


def test_freeze_requires_complete_inventory_and_matching_declared_digest(
    tmp_path: Path,
) -> None:
    plan_path, template_path = _prepared(tmp_path)
    template = ds7_eval.read_json(template_path)
    template["reference_audit"] = "reference_excluded"

    incomplete = {**template, "captures": template["captures"][:-1]}
    incomplete_path = tmp_path / "incomplete.json"
    _write_json(incomplete_path, incomplete)
    with pytest.raises(ValueError, match="account for all 88"):
        ds7_eval.freeze_inputs(plan_path, incomplete_path, tmp_path / "never.json")

    artifact = tmp_path / "synthetic.json"
    _write_json(artifact, {"schema": "synthetic-ds7-test-export/v1", "values": [1, 2]})
    first = template["captures"][0]
    first.update(
        state="ready",
        reason=None,
        artifacts=[
            {
                "kind": "scan_estimate",
                "path": str(artifact),
                "sha256": "sha256:" + "0" * 64,
            }
        ],
    )
    bad_digest_path = tmp_path / "bad-digest.json"
    _write_json(bad_digest_path, template)
    with pytest.raises(ValueError, match="Input changed before freezing"):
        ds7_eval.freeze_inputs(plan_path, bad_digest_path, tmp_path / "also-never.json")


def test_valid_subprocess_run_seals_request_response_and_provenance(tmp_path: Path) -> None:
    run_root = _run(tmp_path, _valid_body())
    receipt = ds7_eval.read_json(run_root / "results.json")
    trial = receipt["results"][0]

    assert trial["response"]["status"] == "ok"
    assert trial["evidence"]["response_validated"] is True
    assert trial["evidence"]["request_sha256"] == ds7_eval.file_digest(
        run_root / "single-001/request.json"
    )
    assert set(trial["evidence"]["files"]) == {
        "request.json",
        "response.json",
        "adapter.log",
    }
    assert receipt["selected_unit_ids"] == ["single-001"]
    assert Path(receipt["resolved_command"][0]).is_absolute()
    code_paths = {row["path"] for row in receipt["code"]}
    assert receipt["resolved_command"][0] in code_paths
    assert receipt["resolved_command"][1] in code_paths
    ds7_eval.read_sealed(run_root / "seal.json", "ds7-run-seal/v1")


@pytest.mark.parametrize(
    ("body", "reason_fragment"),
    [
        ("sys.exit(7)\n", "Adapter exited 7"),
        ("time.sleep(2)\n", "TimeoutExpired"),
    ],
)
def test_failed_and_timed_out_subprocesses_are_accounted(
    tmp_path: Path, body: str, reason_fragment: str
) -> None:
    run_root = _run(tmp_path, body, unit_seconds=0.05 if "sleep" in body else 1.0)
    response = ds7_eval.read_json(run_root / "results.json")["results"][0]["response"]

    assert response["status"] == "failed"
    assert reason_fragment in response["reason"]
    assert (run_root / "seal.json").is_file()


def test_adapter_request_mutation_prevents_run_seal(tmp_path: Path) -> None:
    plan, inputs, _ = _freeze(tmp_path)
    arm, _ = _adapter(
        tmp_path,
        "request['changed_by_synthetic_test']=True\n"
        "request_path.write_text(json.dumps(request))\n" + _valid_body(),
    )
    output = tmp_path / "run"

    with pytest.raises(ValueError, match="modified its request"):
        ds7_eval.run(plan, inputs, arm, output, max_seconds=3, unit_seconds=2)
    assert not (output / "seal.json").exists()


def test_scoring_rejects_tampered_sealed_run(tmp_path: Path) -> None:
    run_root = _run(tmp_path, _valid_body())
    with (run_root / "single-001/adapter.log").open("a") as stream:
        stream.write("tampered after seal\n")

    with pytest.raises(ValueError, match="Run artifact changed"):
        ds7_eval.evaluate(ds7_eval.DEFAULT_DATASET, run_root, tmp_path / "scores")


def test_scoring_keeps_boundary_and_abstention_in_all_attempt_denominator(
    tmp_path: Path,
) -> None:
    body = (
        "unit=request['unit']['unit_id']\n"
        "if unit == 'single-003':\n"
        " response={'schema':'ds7-response/v1','unit_id':unit,'status':'abstained',"
        "'reason':'synthetic_test_abstention','estimate':None}\n"
        "else:\n"
        " response={'schema':'ds7-response/v1','unit_id':unit,'status':'ok',"
        "'estimate':{'latitude_deg':0.25,'longitude_deg':-0.5},'converged':True,"
        "'boundary_hit':unit == 'single-002','horizontal_radius_95_m':2000.0}\n"
        "response_path.write_text(json.dumps(response))\n"
    )
    run_root = _run(
        tmp_path,
        body,
        suite="standard",
        ready_count=3,
        selected_units=["single-001", "single-002", "single-003"],
    )
    output = tmp_path / "scores"
    ds7_eval.evaluate(ds7_eval.DEFAULT_DATASET, run_root, output)
    scores = ds7_eval.read_sealed(output / "scores.json", "ds7-score/v1")
    summary = scores["by_kind"]["single"]

    assert summary["attempted"] == 3
    assert summary["qualified"] == 1
    assert summary["boundary_count"] == 1
    assert summary["unconverged_count"] == 0
    assert summary["states"] == {"abstained": 1, "ok": 2}
    assert summary["availability"] == pytest.approx(1 / 3)
    qualified_error = next(
        row["horizontal_error_m"] for row in scores["trials"] if row["qualified"]
    )
    assert summary["fraction_below_1km_all_attempts"] == pytest.approx(
        (1 if qualified_error < 1000 else 0) / 3
    )
    assert scores["selected_unit_ids"] == ["single-001", "single-002", "single-003"]
    ds7_eval.read_sealed(output / "seal.json", "ds7-run-seal/v1")


def test_source_reader_port_rejects_wrong_manifest() -> None:
    capture = {"session_id": "synthetic", "manifest_sha256": "sha256:expected"}
    reader = SimpleNamespace(inspect=lambda sid: SimpleNamespace(manifest_sha256="sha256:other"))
    with pytest.raises(ValueError, match="Source manifest changed"):
        ds7_eval.load_recording(capture, reader)


def test_frozen_artifact_mutation_prevents_execution(tmp_path: Path) -> None:
    plan, inputs, _ = _freeze(tmp_path)
    arm, _ = _adapter(tmp_path, _valid_body())
    artifact = ds7_eval.read_json(inputs)["captures"][0]["artifacts"][0]
    Path(artifact["path"]).write_text("changed\n")
    with pytest.raises(ValueError, match="Frozen input changed"):
        ds7_eval.run(plan, inputs, arm, tmp_path / "run")
    assert not (tmp_path / "run").exists()


def test_named_reference_field_is_rejected() -> None:
    with pytest.raises(ValueError, match="Reference-bearing field"):
        ds7_eval.reject_reference_fields({"calibration": {"reference_latitude_deg": 0.0}})


def test_unavailable_members_are_not_silently_dropped(tmp_path: Path) -> None:
    run_root = _run(tmp_path, _valid_body(), suite="standard", selected_units=["group8-01"])
    response = ds7_eval.read_json(run_root / "results.json")["results"][0]["response"]
    assert response["status"] == "unavailable"
    assert len(response["missing_session_ids"]) == 7
    assert not (run_root / "group8-01").exists()


def test_malformed_response_is_sealed_as_failure(tmp_path: Path) -> None:
    run_root = _run(tmp_path, "response_path.write_text('not json')\n")
    result = ds7_eval.read_json(run_root / "results.json")["results"][0]
    assert result["response"]["status"] == "failed"
    assert not result["evidence"]["response_validated"]
    ds7_eval.evaluate(ds7_eval.DEFAULT_DATASET, run_root, tmp_path / "scores")


def test_horizontal_metric_handles_dateline_and_antipodes() -> None:
    assert ds7_eval.horizontal_error_m(0, 179.999, 0, -179.999) == pytest.approx(
        222.39016, rel=1e-6
    )
    assert ds7_eval.horizontal_error_m(0, 0, 0, 180) > 20_000_000
    assert ds7_eval.horizontal_error_m(90, 0, 90, 0) == 0


@pytest.mark.parametrize("method", ["equal", "inverse_rms2", "lowest_rms75"])
def test_controls_preserve_bindings_and_average_across_dateline(
    tmp_path: Path, method: str
) -> None:
    inputs = []
    for i, lon in enumerate([179.99, -179.99, 179.98, -179.98]):
        path = tmp_path / f"scan-{i}.json"
        _write_json(
            path,
            {
                "schema": "ds7-scan-estimate/v1",
                "session_id": str(i),
                "manifest_sha256": "sha256:synthetic",
                "status": "ok",
                "estimate": {"latitude_deg": 0.0, "longitude_deg": lon},
                "converged": True,
                "boundary_hit": False,
                "rf_rms_hz": i + 1,
            },
        )
        inputs.append(
            {
                "session_id": str(i),
                "manifest_sha256": "sha256:synthetic",
                "artifacts": [{"kind": "scan_estimate", "path": str(path)}],
            }
        )
    request = {"unit": {"unit_id": "synthetic"}, "inputs": inputs, "config": {"method": method}}
    response = ds7_position_controls.estimate(request)
    assert response["status"] == "ok"
    assert abs(response["estimate"]["longitude_deg"]) > 179.9
    assert len(response["diagnostics"]["used_session_ids"]) == (
        3 if method == "lowest_rms75" else 4
    )
    upstream = ds7_eval.read_json(Path(inputs[0]["artifacts"][0]["path"]))
    upstream["boundary_hit"] = True
    _write_json(Path(inputs[0]["artifacts"][0]["path"]), upstream)
    assert ds7_position_controls.estimate(request)["status"] == "abstained"


def test_unready_research_arm_is_rejected(tmp_path: Path) -> None:
    plan, inputs, _ = _freeze(tmp_path)
    with pytest.raises(ValueError, match="Arm is not ready"):
        ds7_eval.run(plan, inputs, ds7_eval.REPO / "config/ds7/baseline.json", tmp_path / "run")


def test_runner_preserves_virtualenv_executable_path(tmp_path: Path) -> None:
    plan, inputs, _ = _freeze(tmp_path)
    arm_path, _ = _adapter(tmp_path, _valid_body())
    arm = ds7_eval.read_json(arm_path)
    executable = tmp_path / "venv-bin-python"
    executable.symlink_to(sys.executable)
    arm["command"][0] = str(executable)
    _write_json(arm_path, arm)
    output = tmp_path / "run"
    ds7_eval.run(plan, inputs, arm_path, output, max_seconds=3, unit_seconds=2)
    receipt = ds7_eval.read_json(output / "results.json")
    assert receipt["resolved_command"][0] == str(executable)
    assert receipt["results"][0]["response"]["status"] == "ok"
