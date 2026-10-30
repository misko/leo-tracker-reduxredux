"""ALGO03 production isolation, source provenance, fallback and restart checks."""

import copy
import json
import time
from argparse import Namespace

import algo03_production_worker as worker
import pytest
from algo03_production_worker import envelope
from run_algo03_snapshot import copy_snapshot

from leo.application.automatic_fast_graph_v2 import process
from leo.contracts.digests import canonical_digest
from leo.contracts.fast_graph_position import CENTER, KIND, MODEL_VERSION
from leo.storage.fast_graph_position import FastGraphPositionStore
from leo.storage.fast_graph_position_v2 import FastGraphPositionStoreV2
from leo.storage.fast_scan import immutable_json
from leo.storage.graph_position_view import GraphPositionView


def setup(tmp_path):
    inventory = dict(
        schema_version=1,
        kind="fast-scan-source",
        recording_name="capture",
        segments=[dict(scope="segment", manifest_digest="sha256:manifest")],
    )
    digest = canonical_digest(inventory)
    session = "fast-" + digest[7:39]
    immutable_json(tmp_path / "fast-scan-inputs" / (session + ".json"), inventory)
    source = dict(session_id=session, input_manifest_sha256=digest, capture_mode="adaptive")
    immutable_json(tmp_path / "fast-scan-tracking-inputs/run.json", dict(source=source))
    baseline = FastGraphPositionStore(tmp_path)
    source_job = next(baseline.inputs())
    arm = dict(
        endpoint_latlon=list(CENTER),
        endpoint_east_north_km=[0.0, 0.0],
        gates=dict(
            tracks=[
                dict(component="track", points=1, compatible=True, observation_ids=["old"], norad=1)
            ]
        ),
        linear_gates=[],
        final_phase_change_s=0.0,
        RMS_hz=100.0,
        negative_twice_elbo=1000.0,
    )
    terminal = dict(
        schema_version=1,
        kind=KIND,
        model_version=MODEL_VERSION,
        input_sha256=source_job["input_sha256"],
        state="complete",
        session_id=session,
        qualification="paired_residual_phase_regional_gates",
        matched_c_inputs=True,
        arms={a: copy.deepcopy(arm) for a in ("c0", "fitted_c")},
        elapsed_seconds=100.0,
        reference_usage="none",
        future_TLE_used=False,
        selected_arm="fitted_c",
        read_audit=dict(
            receipts=4,
            denied_paths=[],
            historical_result_or_GPS_reads=False,
            all_launched_processes_accounted=True,
        ),
        position=dict(latitude_deg=CENTER[0], longitude_deg=CENTER[1]),
    )
    immutable_json(baseline.path(source_job["job_id"]) / "output/terminal.json", terminal)
    baseline.update(source_job, state="complete")
    candidate = FastGraphPositionStoreV2(tmp_path, baseline=baseline)
    return baseline, candidate, source_job, terminal


def test_only_new_completed_digest_verified_fast_baselines_are_admitted(tmp_path):
    baseline, store, source, terminal = setup(tmp_path)
    job = next(store.inputs(minimum_completed_utc_ns=1))
    assert job["job_id"] != source["job_id"]
    assert store.namespace != baseline.namespace
    assert job["fast_acquisition"]["kind"] == "fast-scan-source"
    # Fast exports carry a compatibility capture_mode=adaptive; ingress authority wins.
    store.verify_input(job)
    assert list(store.inputs(minimum_completed_utc_ns=time.time_ns() + 1_000_000)) == []
    with pytest.raises(ValueError):
        list(store.inputs(minimum_completed_utc_ns=0))
    before = (baseline.path(source["job_id"]) / "output/terminal.json").read_bytes()
    result = envelope(terminal, dict(failure="RF rejected"), recovery_seconds=2.0)
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        output = store.path(job["job_id"]) / "output"
        output.mkdir()
        immutable_json(output / "terminal.json", result)
        return 0

    assert process(job, store=store, command=["worker"], runner=runner)["state"] == "complete"
    store.update(job, state="running")
    assert process(job, store=store, command=["worker"], runner=runner)["state"] == "complete"
    assert len(calls) == 1
    assert (baseline.path(source["job_id"]) / "output/terminal.json").read_bytes() == before


def test_changed_baseline_cannot_be_recovered_or_published(tmp_path):
    baseline, store, source, _ = setup(tmp_path)
    job = store.job(source)
    path = baseline.path(source["job_id"]) / "output/terminal.json"
    document = json.loads(path.read_text())
    document["elapsed_seconds"] += 1
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="baseline changed"):
        process(
            job, store=store, command=["worker"], runner=lambda *a, **k: pytest.fail("must not run")
        )


def test_interruption_is_durable_and_never_triggers_hidden_retry(tmp_path):
    _, store, source, _ = setup(tmp_path)
    job = store.job(source)
    store.update(job, state="running")
    result = process(
        job, store=store, command=["worker"], runner=lambda *a, **k: pytest.fail("must not run")
    )
    assert result["state"] == "failed"
    assert "no automatic retry" in result["failure"]


def test_view_explicitly_uses_baseline_while_v2_missing_and_exposes_both(tmp_path):
    baseline, candidate, source, terminal = setup(tmp_path)
    view = GraphPositionView(
        tmp_path, candidate.job(source)["model_version"], baseline=baseline, candidate=candidate
    )
    pending = view.detail("run")
    assert pending["fallback"] and pending["decision"] == "ALGO02_fallback"
    assert pending["selected"]["model_version"] == MODEL_VERSION
    job = candidate.job(source)
    document = envelope(terminal, dict(failure="Ambiguous recovery"), recovery_seconds=4.0)
    immutable_json(candidate.path(job["job_id"]) / "output/terminal.json", document)
    candidate.update(job, state="complete")
    selected = view.detail("run")
    assert selected["fallback"]
    assert selected["selected"]["model_version"] == job["model_version"]
    assert selected["baseline"]["position"] == selected["selected"]["position"]
    assert selected["reason"] == "Ambiguous recovery"


def test_bare_adaptive_input_is_rejected_even_with_valid_baseline(tmp_path):
    _, store, source, _ = setup(tmp_path)
    path = tmp_path / "fast-scan-tracking-inputs/run.json"
    path.write_text(json.dumps(dict(session_id="adaptive", capture_mode="adaptive")))
    with pytest.raises((KeyError, ValueError)):
        store.job(source)


@pytest.mark.parametrize("invalid", ["adaptive", "missing", "corrupt_status"])
def test_ineligible_baseline_is_reported_without_starving_later_fast_input(
    tmp_path, monkeypatch, caplog, invalid
):
    baseline, store, source, _ = setup(tmp_path)
    rejected = dict(source, job_id="bad", input_path=str(tmp_path / "rejected.json"))
    if invalid == "adaptive":
        (tmp_path / "rejected.json").write_text(
            json.dumps(dict(session_id="adaptive", capture_mode="adaptive"))
        )
    baseline.update(rejected, state="complete")
    if invalid == "corrupt_status":
        (baseline.path("bad") / "status.json").write_text("invalid json")
    monkeypatch.setattr(baseline, "inputs", lambda: iter([rejected, source]))
    admitted = list(store.inputs(minimum_completed_utc_ns=1))
    assert [job["source_job"]["job_id"] for job in admitted] == [source["job_id"]]
    assert "Rejected ALGO03 baseline discovery for job bad" in caplog.text


def test_job_and_snapshot_routes_share_launcher_and_count_preparation(tmp_path, monkeypatch):
    baseline, _, source, terminal = setup(tmp_path)
    inference = baseline.path(source["job_id"]) / "output/inference/SCAN"
    inference.mkdir(parents=True)
    (inference / "tracking.json").write_bytes(
        (tmp_path / "fast-scan-tracking-inputs/run.json").read_bytes()
    )
    baseline.export_analysis(source, tmp_path / "evaluation-export")
    calls = []
    monkeypatch.setattr(worker.time, "monotonic", lambda: 1000.0)

    def launch(descriptor, output, *, deadline):
        calls.append((descriptor, deadline))
        return dict(baseline=terminal, selected=None, decision="ALGO02_fallback")

    monkeypatch.setattr(worker, "run_snapshot", launch)
    job_result = worker.run(
        Namespace(
            bulk_root=tmp_path,
            job=source["job_id"],
            snapshot=None,
            output=tmp_path / "job-v2",
            maximum_seconds=1200,
            preparation_seconds=0.0,
        )
    )
    snapshot_result = worker.run(
        Namespace(
            bulk_root=tmp_path,
            job=None,
            snapshot=tmp_path / "evaluation-export/descriptor.json",
            output=tmp_path / "snapshot-v2",
            maximum_seconds=1200,
            preparation_seconds=5.0,
        )
    )
    assert calls[0][1] == 2200.0 and calls[1][1] == 2195.0
    assert job_result["position"] == snapshot_result["position"] == terminal["position"]
    assert job_result["decision"] == snapshot_result["decision"] == "ALGO02_fallback"
    assert snapshot_result["recovery_seconds"] == job_result["recovery_seconds"] + 5.0


def test_snapshot_copy_revalidates_input_and_rejects_changed_members(tmp_path):
    baseline, _, source, _ = setup(tmp_path)
    inference = baseline.path(source["job_id"]) / "output/inference/SCAN"
    inference.mkdir(parents=True)
    (inference / "tracking.json").write_bytes(
        (tmp_path / "fast-scan-tracking-inputs/run.json").read_bytes()
    )
    baseline.export_analysis(source, tmp_path / "evaluation-export")
    descriptor = tmp_path / "evaluation-export/descriptor.json"
    copied = copy_snapshot(descriptor, tmp_path / "copied")
    assert copied["root"] == str(tmp_path / "copied/inference")
    (tmp_path / "evaluation-export/inference/SCAN/tracking.json").write_text("changed")
    with pytest.raises(ValueError, match="Snapshot source changed"):
        copy_snapshot(descriptor, tmp_path / "rejected-copy")
