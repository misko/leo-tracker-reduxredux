"""Production execution and paired acceptance checks without hardware."""

import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from leo.application.automatic_fast_graph import process
from leo.contracts.fast_graph_position import KIND, MODEL_VERSION, CENTER, validate_terminal
from leo.storage.fast_graph_position import FastGraphPositionStore, sha


def terminal(digest):
    saved = dict(endpoint_latlon=list(CENTER), endpoint_east_north_km=[0., 0.],
                 gates=dict(tracks=[dict(component="track", points=12, compatible=True)]), linear_gates=[],
                 final_phase_change_s=0., RMS_hz=100., negative_twice_elbo=1000.)
    return dict(schema_version=1, kind=KIND, model_version=MODEL_VERSION,
                input_sha256=digest, state="complete", qualification="paired_residual_phase_regional_gates",
                matched_c_inputs=True, arms={a: copy.deepcopy(saved) for a in ("c0", "fitted_c")},
                reference_usage="none", future_TLE_used=False, selected_arm="fitted_c", session_id="session",
                read_audit=dict(receipts=4, denied_paths=[], historical_result_or_GPS_reads=False,
                                all_launched_processes_accounted=True),
                position=dict(latitude_deg=CENTER[0], longitude_deg=CENTER[1]))


def setup(tmp_path):
    root = tmp_path / "bulk"
    source = root / "fast-scan-tracking-inputs/scan.json"
    source.parent.mkdir(parents=True)
    source.write_text('{"source": {"session_id": "session"}}')
    store = FastGraphPositionStore(root)
    return store, next(store.inputs()), source


@pytest.mark.parametrize("failure", ["gate", "phase", "region", "coordinates", "nan", "mask", "identity"])
def test_complete_terminal_rejects_unqualified_pair(failure):
    document = terminal("sha256:input")
    saved = document["arms"]["c0"]
    if failure == "gate": saved["gates"]["tracks"][0]["compatible"] = False
    if failure == "phase": saved["final_phase_change_s"] = .02
    if failure == "region": saved["endpoint_east_north_km"] = [13., 0.]
    if failure == "coordinates": saved["endpoint_latlon"][0] += 1
    if failure == "nan": saved["RMS_hz"] = float("nan")
    if failure == "mask": document["matched_c_inputs"] = False
    if failure == "identity": document["model_version"] = "other"
    with pytest.raises(ValueError): validate_terminal(document, input_sha256="sha256:input")


def test_failure_cannot_publish_position():
    document = terminal("sha256:input")
    document["state"] = "failed"
    with pytest.raises(ValueError): validate_terminal(document, input_sha256="sha256:input")


def test_modified_input_never_runs(tmp_path):
    store, job, source = setup(tmp_path)
    source.write_text("changed")
    with pytest.raises(ValueError):
        process(job, store=store, command=["worker"], runner=lambda *a, **k: pytest.fail("must not run"))


def test_process_and_restart_recover_terminal_without_refit(tmp_path):
    store, job, _ = setup(tmp_path)
    calls = []
    def runner(command, **kwargs):
        calls.append(command)
        out = Path(command[command.index("--output") + 1])
        out.mkdir()
        (out / "terminal.json").write_text(json.dumps(terminal(job["input_sha256"])))
        return 0
    assert process(job, store=store, command=["worker"], runner=runner)["state"] == "complete"
    assert len(calls) == 1
    store.update(job, state="running")
    assert process(job, store=store, command=["worker"], runner=runner)["state"] == "complete"
    assert len(calls) == 1


def test_interrupted_job_is_not_automatically_retried(tmp_path):
    store, job, _ = setup(tmp_path)
    store.update(job, state="running")
    assert process(job, store=store, command=["worker"], runner=lambda *a, **k: pytest.fail("must not run"))["state"] == "failed"


def test_changed_input_changes_versioned_job_identity(tmp_path):
    store, job, source = setup(tmp_path)
    source.write_text("different")
    assert next(store.inputs())["job_id"] != job["job_id"]


def test_path_confinement(tmp_path):
    store, _, _ = setup(tmp_path)
    with pytest.raises(ValueError): store.path("../outside")


def test_read_guard_denies_historical_results(tmp_path):
    import os
    guard = Path(__file__).resolve().parents[2] / "deploy/fast_graph_guard"
    run = tmp_path / "run"
    run.mkdir()
    env = dict(os.environ, PYTHONPATH=str(guard), LEO_FAST_GRAPH_RUN_ROOT=str(run),
               LEO_FAST_GRAPH_SOURCE_ROOT=str(guard.parents[1]),
               LEO_FAST_GRAPH_INPUT=str(tmp_path / "tracking.json"), LEO_FAST_GRAPH_TLE_ROOT="/var/lib/leo/tle")
    child = subprocess.run([sys.executable, "-B", "-c", "open('/srv/bulk/leo/research/other/result.json').read()"],
                           env=env, capture_output=True, text=True)
    assert child.returncode != 0 and "unrelated data read" in child.stderr
    receipt = json.loads(next((run / "read_receipts").glob("*.json")).read_text())
    assert "/srv/bulk/leo/research/other/result.json" in receipt["denied_paths"]
