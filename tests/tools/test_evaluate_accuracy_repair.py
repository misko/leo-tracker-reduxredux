"""Experimental worker planning, integrity and bounded admission without RF inference."""

import copy
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import evaluate_accuracy_repair as repair
import pytest


def members():
    return [
        dict(
            dataset_label=case,
            recording_id=group,
            availability=status,
            session_id="session-" + case,
            input_sha256="sha256:" + "1" * 64,
            causal_snapshots={},
        )
        for case, group, status in (
            ("DS26-0012", "diagnostic", "available"),
            ("DS26-0013", "diagnostic", "available"),
            ("DS26-0100", "one", "available"),
            ("DS26-0101", "one", "available"),
            ("DS26-0200", "two", "available"),
            ("DS26-0300", "three", "missing"),
        )
    ]


def manifest(tmp_path, *, cases=("DS26-0100", "DS26-0200"), roles=("baseline", "selective-gap")):
    source = dict(
        root=str(Path(repair.__file__).resolve().parents[1] / "src"), sha256="source", files={}
    )
    template = dict(evaluation_reference={"latitude_deg": 1, "longitude_deg": 2})
    selected_members = [m for m in members() if m["dataset_label"] in cases]
    schedule = [
        dict(
            dataset="DS26",
            case=m["dataset_label"],
            repetition=0,
            group=m["recording_id"],
            split="untouched",
            order=list(roles),
        )
        for m in selected_members
    ]
    return dict(
        schema_version=1,
        model=repair.MODEL,
        source=source,
        worker=repair.__file__,
        python=sys.executable,
        output=str(tmp_path / "outputs"),
        native_manifest={},
        bindings={},
        timeout_seconds=1,
        roles=list(roles),
        policies={role: repair.POLICIES[role] for role in roles},
        schedule=schedule,
        cohorts={
            "DS26": dict(
                snapshot=str(tmp_path / "snapshot"),
                members=selected_members,
                template=template,
                config_sha256="config",
                references={case: template["evaluation_reference"] for case in cases},
            )
        },
        execution_mode="contended",
        timing_scope="complete experimental worker",
    )


def worker_value(request, *, score=12, residual=3):
    arms = {
        arm: dict(
            endpoint_latlon=[1, 2],
            associated_points=1,
            residual_rms_hz=residual,
            frequency_score=score,
            gps_error_km=None,
            owners={"observation": 123},
        )
        for arm in repair.ev.ARMS
    }
    return dict(
        schema_version=1,
        model=repair.MODEL,
        status="complete",
        role=request["role"],
        policy=request["policy"],
        request_sha256=repair.ev.digest(request),
        source_sha256=request["source"]["sha256"],
        native_manifest_sha256=repair.ev.digest(request["native_manifest"]),
        arms=arms,
        prediction_rows={
            arm: [
                dict(
                    observation_id="observation",
                    norad=123,
                    measured_cfo_hz=10,
                    receiver=1,
                    channel=2,
                    time_s=5,
                    residual_hz=residual,
                )
            ]
            for arm in repair.ev.ARMS
        },
        stage_timings=[],
        native_counts={"calls": 4},
        work={"annotation_training_work": {"started": 2}},
    )


def save_artifact(request, worker):
    from leo.contracts.fast_standard_analysis import PLOTS
    from leo.storage.localization_v3_codec import pack

    destination = Path(request["job"]["output_root"])
    destination.mkdir(parents=True, exist_ok=True)
    artifact = destination / "experimental-evidence.zip"
    payload = dict(
        schema_version=1,
        model=repair.MODEL,
        request=request,
        request_sha256=repair.ev.digest(request),
        policy=request["policy"],
        presentation=dict(arms=worker["arms"], rows=worker["prediction_rows"]),
        selected=dict(
            arms={
                arm: dict(negative_twice_elbo=worker["arms"][arm]["frequency_score"])
                for arm in repair.ev.ARMS
            },
            owners={arm: worker["arms"][arm]["owners"] for arm in repair.ev.ARMS},
        ),
        stage_timings=worker["stage_timings"],
        provenance=dict(
            native_backend=dict(receipts=[dict(counts=worker["native_counts"])]),
            annotation_training_work=dict(counts=worker["work"]["annotation_training_work"]),
        ),
    )
    artifact.write_bytes(pack(payload, {name: b"\x89PNG\r\n\x1a\nsynthetic" for name in PLOTS}))
    worker["artifact"] = dict(
        path=str(artifact), sha256=repair.ev.file_digest(artifact), bytes=artifact.stat().st_size
    )


def save_record(document, assignment, role, *, status="complete", wall=10, score=12, residual=3):
    request = repair.worker_request(document, assignment, role)
    folder = Path(document["output"]) / (assignment["case"] + "-r0")
    record = dict(
        status=status,
        role=role,
        request_sha256=repair.ev.digest(request),
        process=dict(wall_seconds=wall, cpu_seconds=wall / 2, cpu_complete=True),
    )
    if status == "complete":
        worker = worker_value(request, score=score, residual=residual)
        save_artifact(request, worker)
        record["worker"] = worker
    repair.write(folder / (role + "-execution.json"), record)
    return record


def test_seeded_holdout_keeps_recordings_whole_and_excludes_diagnostic_siblings():
    a = repair.recording_selection(members(), profile="holdout", seed="frozen", groups=1)
    b = repair.recording_selection(members(), profile="holdout", seed="frozen", groups=1)
    assert a == b
    assert not set(a["cases"]) & {"DS26-0012", "DS26-0013", "DS26-0300"}
    assert "DS26-0100" not in a["cases"] or "DS26-0101" in a["cases"]
    assert a["selection_uses"] == "membership and availability only; no scientific outcomes or GPS"
    with pytest.raises(ValueError, match="whole recording"):
        repair.recording_selection(members(), profile="holdout", seed="frozen", cases="DS26-0100")
    with pytest.raises(ValueError, match="development"):
        repair.recording_selection(
            members(), profile="holdout", seed="frozen", cases="DS26-0012,DS26-0013"
        )


def test_full_retains_missing_and_diagnostic_groups_in_coverage():
    selected = repair.recording_selection(members(), profile="full", seed="frozen")
    assert set(selected["cases"]) == {m["dataset_label"] for m in members()}
    assert selected["missing_cases"] == ["DS26-0300"]
    assert selected["diagnostic_cases"] == ["DS26-0012", "DS26-0013"]
    with pytest.raises(ValueError, match="Diagnostic profile"):
        repair.recording_selection(members(), profile="diagnostic", seed="frozen")


def test_worker_request_never_contains_saved_reference_and_is_same_input_for_all_variants(tmp_path):
    document = manifest(tmp_path, roles=repair.ROLES)
    assignment = document["schedule"][0]
    jobs = []
    for role in repair.ROLES:
        request = repair.worker_request(document, assignment, role)
        assert request["job"]["evaluation_reference"] is None
        assert "references" not in request and "reference" not in request
        job = copy.deepcopy(request["job"])
        for key in ("identity", "output_root"):
            job.pop(key)
        jobs.append(job)
    assert jobs[0] == jobs[1] == jobs[2]
    assert document["cohorts"]["DS26"]["template"]["evaluation_reference"] is not None


def test_saved_frequency_score_survives_evaluation_only_projection(tmp_path):
    document = manifest(tmp_path)
    request = repair.worker_request(document, document["schedule"][0], "baseline")
    worker = worker_value(request, score=-123.5)
    projected = repair.measured_arms(worker, dict(latitude_deg=1, longitude_deg=2))
    assert projected["c0"]["frequency_score"] == -123.5
    assert projected["c0"]["gps_error_km"] == 0
    assert worker["arms"]["c0"].get("gps_error_km") is None


def test_complete_pair_records_matched_residuals_but_failure_never_enters_accuracy_or_timing(
    tmp_path,
):
    document = manifest(tmp_path)
    first, second = document["schedule"]
    save_record(document, first, "baseline", score=10, residual=4)
    save_record(document, first, "selective-gap", wall=12, score=8, residual=2)
    save_record(document, second, "baseline")
    save_record(document, second, "selective-gap", status="timed_out", wall=0.1)
    result = repair.collect(document)
    pair = result["pairs"][0]
    assert pair["arms"]["c0"]["frequency_score"]["delta"] == -2
    assert pair["timing"]["wall_seconds"]["overhead_percent"] == pytest.approx(20)
    matched = pair["arms"]["c0"]["matched_observation_residuals"]
    assert (matched["count"], matched["baseline_rms_hz"], matched["candidate_rms_hz"]) == (1, 4, 2)
    assert "not held-out" in matched["interpretation"]
    assert "arms" not in result["pairs"][1] and "timing" not in result["pairs"][1]
    assert result["coverage_complete"]
    summary = result["summaries"]["DS26/untouched/selective-gap"]
    assert summary["paired_complete"] == 1
    assert summary["statuses"]["candidate"] == {"complete": 1, "timed_out": 1}
    assert summary["arms"]["c0"]["gps_error_km"]["delta"]["count"] == 1


def test_archive_or_request_tampering_stops_resume(tmp_path):
    document = manifest(tmp_path)
    assignment = document["schedule"][0]
    record = save_record(document, assignment, "baseline")
    repair.validate_record(document, assignment, "baseline", record)
    record["worker"]["arms"]["c0"]["frequency_score"] += 1
    with pytest.raises(ValueError, match="metrics differ"):
        repair.validate_record(document, assignment, "baseline", record)
    record["worker"]["arms"]["c0"]["frequency_score"] -= 1
    Path(record["worker"]["artifact"]["path"]).write_bytes(b"changed")
    with pytest.raises(ValueError, match="archive changed"):
        repair.validate_record(document, assignment, "baseline", record)
    record["request_sha256"] = "other"
    with pytest.raises(ValueError, match="request/role"):
        repair.validate_record(document, assignment, "baseline", record)


def test_frozen_tool_and_source_drift_stop_before_inference(tmp_path, monkeypatch):
    document = manifest(tmp_path)
    bound = tmp_path / "bound"
    bound.write_text("original")
    document["bindings"] = {str(bound): repair.ev.file_digest(bound)}
    monkeypatch.setattr(repair.ev, "source_binding", lambda path: document["source"])
    repair.check_bindings(document)
    bound.write_text("changed")
    with pytest.raises(ValueError, match="Frozen input changed"):
        repair.check_bindings(document)
    document["bindings"] = {}
    monkeypatch.setattr(repair.ev, "source_binding", lambda path: {"different": True})
    with pytest.raises(ValueError, match="source tree changed"):
        repair.check_bindings(document)


def test_supervisor_hard_deadline_marks_cpu_incomplete_and_normal_exit_accounts_cpu(tmp_path):
    began = time.monotonic()
    timed = repair.supervise_worker(
        [sys.executable, "-c", "import time; time.sleep(20)"],
        tmp_path / "timeout.log",
        0.1,
        dict(os.environ),
    )
    assert time.monotonic() - began < 2
    assert timed["status"] == "timed_out" and not timed["cpu_complete"]
    normal = repair.supervise_worker(
        [sys.executable, "-c", "sum(range(1000))"], tmp_path / "normal.log", 3, dict(os.environ)
    )
    assert normal["returncode"] == 0 and normal["cpu_complete"]
    assert normal["cpu_seconds"] >= 0


def fake_run(monkeypatch, document):
    calls = []
    monkeypatch.setattr(repair, "bulk_output", lambda path: Path(path))
    monkeypatch.setattr(repair, "check_bindings", lambda manifest: None)

    def supervise(command, log_path, timeout, environment):
        request = repair.ev.read(command[-1])
        calls.append((request["job"]["identity"], request["role"], timeout))
        worker = worker_value(request)
        save_artifact(request, worker)
        destination = Path(request["job"]["output_root"])
        repair.write(destination / "worker-result.json", worker)
        return dict(status="exited", returncode=0, wall_seconds=1, cpu_seconds=1, cpu_complete=True)

    monkeypatch.setattr(repair, "supervise_worker", supervise)
    path = Path(document["output"]).parent / "manifest.json"
    repair.write(path, document)
    return path, calls


def test_bounded_recording_admission_and_resume_never_relaunch_completed_workers(
    tmp_path, monkeypatch
):
    document = manifest(tmp_path)
    path, calls = fake_run(monkeypatch, document)
    cpu = str(min(os.sched_getaffinity(0)))
    assert repair.run(path, cpu, max_recordings=1, max_wall_seconds=10, reserve_gib=0) == 0
    assert len(calls) == 2
    invocation = repair.ev.read(Path(document["output"]) / "invocation.json")
    assert invocation["status"] == "staged" and not invocation["coverage_complete"]
    assert repair.run(path, cpu, max_recordings=1, max_wall_seconds=10, reserve_gib=0) == 0
    assert len(calls) == 4
    assert repair.ev.read(Path(document["output"]) / "invocation.json")["coverage_complete"]
    repair.run(path, cpu, max_recordings=1, max_wall_seconds=10, reserve_gib=0)
    assert len(calls) == 4


def test_insufficient_chunk_budget_never_shortens_scientific_deadline(tmp_path, monkeypatch):
    document = manifest(tmp_path)
    document["timeout_seconds"] = 5
    path, calls = fake_run(monkeypatch, document)
    repair.run(
        path, str(min(os.sched_getaffinity(0))), max_recordings=1, max_wall_seconds=1, reserve_gib=0
    )
    assert not calls
    invocation = repair.ev.read(Path(document["output"]) / "invocation.json")
    assert invocation["status"] == "staged"
    assert "complete worker deadline" in invocation["stop_reason"]


def test_qnap_and_small_root_outputs_rejected():
    with pytest.raises(ValueError, match="QNAP"):
        repair.bulk_output("/mnt/qnap01/forbidden")
    with pytest.raises(ValueError, match="/srv/bulk"):
        repair.bulk_output("/tmp/forbidden")
    assert repair.bulk_output(repair.CACHE / "staging") == repair.CACHE / "staging"


def test_plan_is_deterministic_binds_helpers_and_never_runs_inference(tmp_path, monkeypatch):
    document = manifest(tmp_path, cases=("DS26-0200",))
    snapshot = Path(document["cohorts"]["DS26"]["snapshot"])
    (snapshot / "inputs").mkdir(parents=True)
    repair.write(snapshot / "inputs/config.json", {"config": {}})
    inventory = dict(
        members=members(), config_sha256=repair.ev.file_digest(snapshot / "inputs/config.json")
    )
    repair.write(snapshot / "inventory.json", inventory)
    repair.write(snapshot / "template-request.json", document["cohorts"]["DS26"]["template"])
    paths = {name: tmp_path / name for name in ("binary", "source", "wrapper", "provider")}
    for path in paths.values():
        path.write_text("frozen artifact")
    native = {name: str(path) for name, path in paths.items() if name != "provider"}
    native["provider"] = {"path": str(paths["provider"])}
    native_path = tmp_path / "native.json"
    repair.write(native_path, native)
    cohorts = tmp_path / "cohorts.json"
    repair.write(cohorts, {"DS26": dict(snapshot=str(snapshot), references=None)})
    args = SimpleNamespace(
        output=tmp_path / "outputs",
        source_root=tmp_path,
        cohorts=cohorts,
        native_manifest=native_path,
        roles="selective-gap",
        profile="holdout",
        seed="frozen",
        repeats=1,
        timeout=1200,
        cases=None,
        groups_per_dataset=1,
    )
    monkeypatch.setattr(repair, "bulk_output", lambda path: Path(path))
    monkeypatch.setattr(repair.ev, "source_binding", lambda path: document["source"])
    monkeypatch.setattr(
        repair, "supervise_worker", lambda *args: pytest.fail("Planning cannot run inference")
    )
    planned = repair.prepare(args)
    assert planned == repair.prepare(args)
    assert planned["roles"] == ["baseline", "selective-gap"]
    assert any(name.endswith("initial_discovery_archive.py") for name in planned["bindings"])
    assert planned["cohorts"]["DS26"]["selection"]["diagnostic_cases"] == ["DS26-0012", "DS26-0013"]
    assert not set(row["case"] for row in planned["schedule"]) & {"DS26-0012", "DS26-0013"}
    args.profile = "full"
    full = repair.prepare(args)
    assert {row["case"] for row in full["schedule"]} == {row["dataset_label"] for row in members()}


def test_one_proposal_variant_sets_only_explicit_selector_cap(tmp_path, monkeypatch):
    from leo.analysis.localization_v3 import omitted_track_proposals
    from leo.analysis.localization_v4 import backend
    from leo.operations import (
        localization_v5_controls,
        localization_v5_joint,
        localization_v5_training,
    )

    def constructor(*args):
        return SimpleNamespace()

    monkeypatch.setattr(backend, "ProcessBound", constructor)
    monkeypatch.setattr(localization_v5_training, "ProcessTrainingFit", constructor)
    monkeypatch.setattr(localization_v5_controls, "ControlCacheFactory", constructor)
    monkeypatch.setattr(localization_v5_joint, "JointScheduleFactory", constructor)
    calls = []

    def rank(context, evidence, *, max_proposals=2):
        calls.append((context, evidence, max_proposals))
        return {"targets": list(range(max_proposals))}

    monkeypatch.setattr(omitted_track_proposals, "rank_omitted_tracks", rank)
    one, _ = repair.execution_ports(
        dict(role="omitted-track-one", native_manifest={}), tmp_path, lambda row: None
    )
    two, _ = repair.execution_ports(
        dict(role="omitted-tracks", native_manifest={}), tmp_path, lambda row: None
    )
    baseline, _ = repair.execution_ports(
        dict(role="baseline", native_manifest={}), tmp_path, lambda row: None
    )
    assert one.recovery_target_selector("same context", "same evidence")["targets"] == [0]
    assert two.recovery_target_selector("same context", "same evidence")["targets"] == [0, 1]
    assert calls == [("same context", "same evidence", 1), ("same context", "same evidence", 2)]
    assert baseline.recovery_target_selector is None
    assert one.gap_target_filter is two.gap_target_filter is None
    assert one.recovery_target_limit == two.recovery_target_limit == 0
    assert one.map_recovery_arms is two.map_recovery_arms is baseline.map_recovery_arms


def test_one_proposal_variant_binds_identity_and_preserves_cli_defaults(tmp_path, monkeypatch):
    document = manifest(tmp_path, roles=("baseline", "omitted-tracks", "omitted-track-one"))
    assignment = document["schedule"][0]
    one = repair.worker_request(document, assignment, "omitted-track-one")
    two = repair.worker_request(document, assignment, "omitted-tracks")
    assert one["policy"] == "omitted_uncurved_calibrated_one_experiment_v1"
    assert one["policy"] != two["policy"]
    assert one["job"]["identity"]["run_id"] != two["job"]["identity"]["run_id"]
    assert one["source"] == two["source"] and one["native_manifest"] == two["native_manifest"]
    assert one["model"] == two["model"] == repair.MODEL
    assert one["schema_version"] == two["schema_version"] == 1
    assert repair.DEFAULT_ROLES == ("baseline", "selective-gap", "omitted-tracks")
    captured = []
    monkeypatch.setattr(repair, "prepare", lambda args: captured.append(args.roles) or {})
    monkeypatch.setattr(repair, "bulk_output", lambda path: Path(path))
    repair.main(
        ["plan", "--manifest", str(tmp_path / "plan.json"), "--output", str(tmp_path / "output"),
         "--native-manifest", str(tmp_path / "native.json")]
    )
    assert captured == ["baseline,selective-gap,omitted-tracks"]
    invalid = copy.deepcopy(one)
    invalid["policy"] = two["policy"]
    path = tmp_path / "invalid.json"
    repair.write(path, invalid)
    with pytest.raises(ValueError, match="Bound experimental worker request"):
        repair.execute_worker(path)


def test_validation_cache_rehashes_bytes_and_avoids_redundant_scientific_decode(
    tmp_path, monkeypatch
):
    document = manifest(tmp_path)
    assignment = document["schedule"][0]
    record = save_record(document, assignment, "baseline")
    artifact = Path(record["worker"]["artifact"]["path"])
    original_hash, original_inspect = repair.ev.file_digest, repair.inspect_artifact
    hashes, inspections = [], []

    def hashed(path):
        hashes.append(Path(path))
        return original_hash(path)

    def inspect(request, worker):
        inspections.append(request["policy"])
        return original_inspect(request, worker)

    monkeypatch.setattr(repair.ev, "file_digest", hashed)
    monkeypatch.setattr(repair, "inspect_artifact", inspect)
    assert repair.validate_record(document, assignment, "baseline", record) == "fresh"
    assert repair.validate_record(document, assignment, "baseline", record) == "cached"
    assert len(inspections) == 1 and hashes.count(artifact) == 2
    cache = artifact.with_name("validated-archive.json")
    receipt = repair.ev.read(cache)
    assert receipt["worker_sha256"] == repair.ev.digest(record["worker"])
    assert receipt["validator_sha256"] == original_hash(repair.__file__)
    damaged = bytearray(artifact.read_bytes())
    damaged[-1] ^= 1
    artifact.write_bytes(damaged)
    with pytest.raises(ValueError, match="archive changed"):
        repair.validate_record(document, assignment, "baseline", record)
    assert len(inspections) == 1


def test_validation_cache_corruption_or_validator_change_forces_full_validation(
    tmp_path, monkeypatch
):
    document = manifest(tmp_path)
    assignment = document["schedule"][0]
    record = save_record(document, assignment, "baseline")
    assert repair.validate_record(document, assignment, "baseline", record) == "fresh"
    cache = Path(record["worker"]["artifact"]["path"]).with_name("validated-archive.json")
    cache.write_text("not valid JSON")
    assert repair.validate_record(document, assignment, "baseline", record) == "fresh"
    original_hash = repair.ev.file_digest

    def changed_validator(path):
        return "sha256:" + "a" * 64 if Path(path) == Path(repair.__file__) else original_hash(path)

    monkeypatch.setattr(repair.ev, "file_digest", changed_validator)
    assert repair.validate_record(document, assignment, "baseline", record) == "fresh"
    assert repair.validate_record(document, assignment, "baseline", record) == "cached"
    record["worker"]["prediction_rows"]["c0"][0]["residual_hz"] += 1
    with pytest.raises(ValueError, match="metrics differ"):
        repair.validate_record(document, assignment, "baseline", record)


def test_validation_cache_cannot_escape_worker_directory_or_write_to_qnap(tmp_path):
    document = manifest(tmp_path)
    assignment = document["schedule"][0]
    record = save_record(document, assignment, "baseline")
    artifact = Path(record["worker"]["artifact"]["path"])
    cache = artifact.with_name("validated-archive.json")
    other = tmp_path / "other.json"
    other.write_text("preserve")
    cache.symlink_to(other)
    with pytest.raises(ValueError, match="cache escaped"):
        repair.validate_record(document, assignment, "baseline", record)
    assert other.read_text() == "preserve"
    request = repair.worker_request(document, assignment, "baseline")
    request["job"]["output_root"] = "/mnt/qnap01/forbidden"
    with pytest.raises(ValueError, match="QNAP"):
        repair.inspect_artifact_cached(request, record["worker"])
