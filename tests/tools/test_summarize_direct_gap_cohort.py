"""The cohort collector validates evidence and keeps partial coverage visible."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import summarize_direct_gap_cohort as collector


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def sha(path):
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return "sha256:" + hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def fixture(tmp_path, monkeypatch):
    frozen = tmp_path / "frozen"
    stage = frozen / "stage"
    report_dir = tmp_path / "owned-summary"
    runner_path = frozen / "runner.py"
    runner_path.parent.mkdir(parents=True)
    runner_path.write_text("frozen runner")
    policy = {"id": "direct-timing-gap-v1"}
    native_paths = {key: frozen / f"{key}.bin" for key in ("binary", "source", "wrapper")}
    native_paths["provider"] = frozen / "provider.bin"
    for path in native_paths.values():
        path.write_text("same native implementation")
    backend_manifest = {key: str(path) for key, path in native_paths.items() if key != "provider"}
    backend_manifest["provider"] = {"path": str(native_paths["provider"])}
    base_role = {"source": {"root": str(frozen / "source")},
                 "evaluator": str(frozen / "evaluator.py"),
                 "backend_manifest": backend_manifest, "initial": None}
    assignments = [{"case": case, "repetition": 0, "order": ["baseline", "candidate"]}
                   for case in ("DS26-0001", "DS29-0001")]
    manifest = {"profile": "full", "schema_version": 4, "fast_flags": {"limit": 0},
                "historical_baseline_root": None, "output": str(stage),
                "snapshot": str(frozen / "snapshot"), "archive_root": None,
                "repeats": 1, "selection": {"cases": ["DS26-0001", "DS29-0001"]},
                "members": [{"dataset_label": case, "recording_id": case,
                             "availability": "available"} for case in ("DS26-0001", "DS29-0001")],
                "schedule": assignments,
                "roles": {"baseline": base_role, "candidate": dict(base_role, direct_gap=policy)}}
    manifest_path = frozen / "manifest.json"
    write(manifest_path, manifest)
    request = {"job": {"evaluation_reference": None, "output_root": "/unused",
                       "identity": {"run_id": "run-one"}},
               "recovery_target_policy": {"maximum_targets": 0},
               "direct_gap_policy": None}
    gap = {"policy": policy, "targets": [{"track_id": "parent-track"}],
           "trials": [{"qualification": {"reasons": [], "qualified": True}}],
           "excluded": [], "stages": [{"name": "gap-prepare", "status": "complete",
                                       "seconds": 2.5}],
           "candidate": {"target_ids": ["new"]},
           "numerical_receipts": {"gap-prepare": {}},
           "no_GPS_inference": True, "causal_only": True,
           "selected": {"track_id": "parent-track", "branch_id": "branch-one",
                        "qualification": {"qualified": True}}}
    store = SimpleNamespace(load=lambda run_id: {"evidence": {"audit": {"gap_recovery": gap}}})
    evaluator = SimpleNamespace(owned_import=lambda name, source: SimpleNamespace(
        LocalizationV5Store=lambda root: store))
    runner = SimpleNamespace(__file__=str(runner_path), FAST_FLAGS=manifest["fast_flags"],
                             PYTHON="/python", ENVIRONMENT={}, sha=sha, digest=digest,
                             read=lambda path: json.loads(Path(path).read_text()), write=write,
                             check_bindings=lambda m: None, evaluator=lambda path: evaluator,
                             command=lambda m, a, side, dest, cpu: ["taskset", "-c", cpu, side],
                             validate_report=lambda report, m, a, side, **kwargs:
                             report["results"][0])
    monkeypatch.setattr(collector, "load_runner", lambda path: runner)

    def inspect(command, **kwargs):
        target = Path(command[command.index("--output") + 1])
        report_path = Path(command[command.index("--report") + 1])
        source_report = json.loads(report_path.read_text())
        row = source_report["results"][0]
        request_path = Path(row["request_path"])
        work = {"public_store_validated": True,
                "manifest_sha256": digest(json.loads(manifest_path.read_text())),
                "report_sha256": sha(report_path),
                "request_sha256": digest(json.loads(request_path.read_text())),
                "result_sha256": row["result_sha256"], "native_counts": {"calls": 7}}
        request = json.loads(request_path.read_text())
        if request["direct_gap_policy"] is not None:
            work["direct_gap_recovery"] = {
                "targets": gap["targets"], "trial_count": len(gap["trials"]),
                "stages": gap["stages"],
                "selected": ({"track_id": "parent-track", "branch_id": "branch-one",
                              "qualified": True}
                             if gap["selected"] else None),
                "native_receipt_stages": sorted(gap["numerical_receipts"])}
        write(target, work)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(collector.subprocess, "run", inspect)
    for side in collector.SIDES:
        folder = stage / "DS26-0001-r0"
        write(folder / f"{side}-execution.json",
              {"command": ["taskset", "-c", "21", side], "returncode": 0, "after": {}})
        actual_request = dict(request, direct_gap_policy=policy if side == "candidate" else None)
        request_path = folder / side / "request.json"
        write(request_path, actual_request)
        owners = {"old": "sat-a"} if side == "baseline" else {"old": "sat-a", "new": "sat-b"}
        arms = {arm: {"owners": owners, "gps_error_km": 4.0 if side == "baseline" else 3.0,
                      "frequency_score": 20.0 if side == "baseline" else 18.0,
                      "residual_rms_hz": 5.0 if side == "baseline" else 4.0,
                      "associated_points": 10 if side == "baseline" else 11}
                for arm in collector.ARMS}
        row = {"case": "DS26-0001", "status": "complete", "request_path": str(request_path),
               "result_sha256": "sha256:result", "arms": arms}
        write(folder / side / "report.json",
              {"plan": {"jobs": [{"request": actual_request}]}, "results": [row]})
    pending = stage / "DS29-0001-r0"
    write(pending / "candidate-execution.json", {"command": ["taskset", "-c", "21", "candidate"]})
    return manifest_path, runner_path, report_dir, stage, gap


def test_partial_population_and_accepted_owner_are_reported(tmp_path, monkeypatch):
    manifest, runner, output, stage, _ = fixture(tmp_path, monkeypatch)
    before = {p: sha(p) for p in stage.rglob("*.json")}
    result = collector.summarize(manifest, runner, output)
    assert result["expected_count"] == 2
    assert result["independent_recordings"] == 2
    assert result["candidate_coverage_complete"] is False
    assert result["paired_coverage_complete"] is False
    assert result["statuses"] == {"baseline": {"absent": 1, "complete": 1},
                                   "candidate": {"complete": 1, "pending": 1}}
    assert result["scientific_failures"] == []
    pair = result["members"][0]["repetitions"][0]
    assert pair["comparison"]["arms"]["c0"]["gps_error_km"]["delta"] == -1
    assert pair["comparison"]["owner_changes"]["c0"]["added"] == ["new"]
    assert pair["comparison"]["owner_changes"]["c0"]["accepted_additions"] == ["new"]
    assert pair["roles"]["candidate"]["gap"]["inner_stage_total_seconds"] == 2.5
    assert pair["roles"]["candidate"]["gap"]["outcome"] == "accepted"
    assert result["gap_outcomes_by_recording"] == {"accepted": 1, "unavailable": 1}
    assert result["cost_by_recording"]["delta"]["recording_count"] == 1
    assert all(sha(path) == old for path, old in before.items())
    assert (output / "summary.json").exists()
    assert collector.summarize(manifest, runner, output)["statuses"] == result["statuses"]


def test_actual_request_tamper_is_rejected(tmp_path, monkeypatch):
    manifest, runner, output, stage, _ = fixture(tmp_path, monkeypatch)
    request = stage / "DS26-0001-r0/candidate/request.json"
    changed = json.loads(request.read_text())
    changed["job"]["evaluation_reference"] = {"latitude": 1}
    write(request, changed)
    with pytest.raises(ValueError, match="Actual request policy differs"):
        collector.summarize(manifest, runner, output)


def test_rejected_gap_and_owner_identity_changes(tmp_path, monkeypatch):
    _, _, _, _, gap = fixture(tmp_path, monkeypatch)
    gap["selected"] = None
    gap["trials"][0]["qualification"] = {"qualified": False, "reasons": ["RF gate"]}
    result = collector.gap_summary(gap, {"selected": None, "targets": gap["targets"],
                                         "trial_count": 1, "stages": gap["stages"],
                                         "native_receipt_stages": []})
    assert result["qualified"] is False
    assert result["outcome"] == "fit_rejected"
    assert result["exclusion_reason_categories"] == {"RF gate": 1}
    base = {"native_counts": {"calls": 4}, "owners": {arm: {"old": "sat-a"}
            for arm in collector.ARMS}, "arms": {arm: {metric: 1 for metric in collector.METRICS}
            for arm in collector.ARMS}}
    candidate = {"native_counts": {"calls": 6}, "gap": result,
                 "owners": {arm: {"old": "sat-b"} for arm in collector.ARMS},
                 "arms": base["arms"]}
    comparison = collector.paired(base, candidate)
    assert comparison["owner_changes"]["c0"]["identity_changed"] == {
        "old": {"baseline": "sat-a", "candidate": "sat-b"}}
    assert comparison["owner_changes"]["c0"]["added"] == []
    candidate["owners"] = {arm: {"old": "sat-b", "new": "sat-c"}
                           for arm in collector.ARMS}
    comparison = collector.paired(base, candidate)
    assert comparison["owner_changes"]["c0"]["added"] == ["new"]
    assert comparison["owner_changes"]["c0"]["accepted_additions"] == []


def test_gap_outcomes_preserve_identity_stage_and_budget_evidence(tmp_path, monkeypatch):
    _, _, _, _, gap = fixture(tmp_path, monkeypatch)
    gap["selected"] = None
    gap["trials"] = []
    gap["excluded"] = [{"track_id": "parent-track", "branch_id": "branch-one",
                        "identity": {"status": "RF_rejected", "reason": "weak RF"}}]
    projected = {"selected": None, "native_receipt_stages": []}
    identity = collector.gap_summary(gap, projected)
    assert identity["outcome"] == "identity_rejected"
    assert identity["exclusion_reason_categories"] == {"weak RF": 1}
    assert identity["excluded"] == gap["excluded"]
    gap["excluded"] = []
    gap["stages"] = [{"name": "gap-0-annotation", "status": "failed",
                      "seconds": 240.0, "timeout_s": 240}]
    failed = collector.gap_summary(gap, projected)
    assert failed["outcome"] == "stage_failed"
    assert failed["stages"] == gap["stages"]
    gap["stages"] = []
    gap["excluded"] = [{"budget_exhausted": "conditional gap recovery deadline"}]
    exhausted = collector.gap_summary(gap, projected)
    assert exhausted["outcome"] == "stage_failed"
    assert exhausted["excluded"] == gap["excluded"]
    assert exhausted["exclusion_reason_categories"] == {"budget_exhausted": 1}
    gap["excluded"] = []
    assert collector.gap_summary(gap, projected)["outcome"] == "inconclusive"


def test_unpaired_rejected_candidate_cost_with_absent_baseline(tmp_path, monkeypatch):
    manifest, runner, output, stage, gap = fixture(tmp_path, monkeypatch)
    gap["selected"] = None
    gap["trials"][0]["qualification"] = {"qualified": False, "reasons": ["RF gate"]}
    gap["stages"][0]["seconds"] = 99.0
    (stage / "DS26-0001-r0/baseline/report.json").unlink()
    (stage / "DS26-0001-r0/baseline-execution.json").unlink()
    result = collector.summarize(manifest, runner, output)
    assert result["statuses"]["baseline"] == {"absent": 2}
    assert result["candidate_coverage_complete"] is False
    assert result["paired_coverage_complete"] is False
    assert result["scientific_failures"] == []
    assert result["gap_outcomes_by_recording"] == {"fit_rejected": 1, "unavailable": 1}
    assert result["cost_by_recording"]["inner_stage_total_seconds"]["recording_count"] == 1
    assert result["cost_by_recording"]["inner_stage_total_seconds"]["median"] == 99.0
    assert result["cost_by_recording"]["candidate"]["recording_count"] == 1
    assert result["cost_by_recording"]["delta"]["recording_count"] == 0
    assert result["accuracy_and_fit_by_recording"]["c0"]["gps_error_km"]["delta"][
        "recording_count"] == 0


def test_terminal_worker_without_report_counts_as_attempted(tmp_path, monkeypatch):
    manifest_path, runner, output, stage, _ = fixture(tmp_path, monkeypatch)
    manifest = json.loads(manifest_path.read_text())
    manifest["members"] = manifest["members"][:1]
    manifest["schedule"] = manifest["schedule"][:1]
    manifest["selection"]["cases"] = ["DS26-0001"]
    write(manifest_path, manifest)
    (stage / "DS26-0001-r0/baseline/report.json").unlink()
    result = collector.summarize(manifest_path, runner, output)
    assert result["expected_count"] == 1
    assert result["statuses"] == {"baseline": {"failed": 1},
                                   "candidate": {"complete": 1}}
    assert result["candidate_coverage_complete"] is True
    assert result["paired_coverage_complete"] is True
    assert result["scientific_failures"][0]["reason"] == "evaluator_no_report"
    assert result["accuracy_and_fit_by_recording"]["c0"]["gps_error_km"]["delta"][
        "recording_count"] == 0


def test_position_delta_tails_and_one_meter_change_counts():
    values = [-0.003, -0.001, 0.0, 0.001, 0.004]
    groups = {str(index): [{"repetitions": [{"comparison": {"delta": value}}]}]
              for index, value in enumerate(values)}
    distribution = collector.independent_distribution(
        groups, lambda pair: pair["comparison"]["delta"], position_delta=True)
    assert distribution["recording_count"] == 5
    assert distribution["denominator_recordings"] == 5
    assert distribution["measured_repetitions"] == 5
    assert distribution["scope"] == "complete_pairs"
    assert distribution["p90"] == pytest.approx(0.0028)
    assert distribution["p95"] == pytest.approx(0.0034)
    assert (distribution["improvement_count"], distribution["tie_count"],
            distribution["regression_count"]) == (1, 3, 1)
    assert distribution["tie_threshold_m"] == 1.0


def test_no_trigger_and_failed_control_stay_distinct(tmp_path, monkeypatch):
    manifest, runner, output, stage, gap = fixture(tmp_path, monkeypatch)
    gap.update(targets=[], trials=[], candidate=None, selected=None, stages=[],
               numerical_receipts={})
    report_path = stage / "DS26-0001-r0/candidate/report.json"
    report = json.loads(report_path.read_text())
    report["results"][0]["arms"] = json.loads(
        (stage / "DS26-0001-r0/baseline/report.json").read_text()
    )["results"][0]["arms"]
    write(report_path, report)
    control = stage / "DS29-0001-r0"
    write(control / "baseline-execution.json",
          {"command": ["taskset", "-c", "21", "baseline"], "returncode": 1, "after": {}})
    write(control / "baseline/report.json",
          {"results": [{"case": "DS29-0001", "status": "failed"}]})
    result = collector.summarize(manifest, runner, output)
    assert result["gap_outcomes_by_recording"] == {"no_trigger": 1, "unavailable": 1}
    assert result["scientific_failures"] == [{"case": "DS29-0001", "repetition": 0,
                                               "side": "baseline", "status": "failed",
                                               "reason": None}]
    assert result["statuses"]["baseline"] == {"complete": 1, "failed": 1}
    assert result["members"][0]["repetitions"][0]["comparison"]["owner_changes"]["c0"][
        "added"] == []


def test_historical_baseline_reads_original_without_writing_it(tmp_path, monkeypatch):
    manifest_path, runner_path, output, stage, _ = fixture(tmp_path, monkeypatch)
    runner = collector.load_runner(runner_path)
    manifest = json.loads(manifest_path.read_text())
    original = tmp_path / "historical-original"
    manifest.update(schema_version=5, historical_baseline_root=str(original),
                    timeout=2400, references=None, bindings={})
    manifest["roles"]["baseline"] = dict(manifest["roles"]["baseline"],
                                         source={"root": str(tmp_path / "old-source")},
                                         evaluator=str(tmp_path / "old-evaluator.py"),
                                         native_manifest=str(tmp_path / "old-native.json"))
    write(manifest_path, manifest)
    write(original / "protocol.json", {
        "snapshot": manifest["snapshot"],
        "cases": [m["dataset_label"] for m in manifest["members"]],
        "sources": {"candidate": manifest["roles"]["baseline"]["source"]},
        "candidate_limit": 0, "timeout": 2400, "references": None, "bindings": {}})
    manifest["bindings"][str(original / "protocol.json")] = sha(original / "protocol.json")
    write(manifest_path, manifest)
    staged = stage / "DS26-0001-r0/baseline"
    original_case = original / "DS26-0001-r0"
    request = json.loads((staged / "request.json").read_text())
    original_request = original_case / "candidate/request.json"
    write(original_request, request)
    report = json.loads((staged / "report.json").read_text())
    report["results"][0]["request_path"] = str(original_request)
    write(original_case / "candidate/report.json", report)
    original_output = str(original_case / "candidate")
    flags = {"--snapshot": manifest["snapshot"], "--cases": "DS26-0001",
             "--profile": "quick", "--version": "algo07v5",
             "--source-root": manifest["roles"]["baseline"]["source"]["root"],
             "--native-manifest": manifest["roles"]["baseline"]["native_manifest"],
             "--output": original_output, "--timeout": "2400", "limit": 0}
    command = [manifest["roles"]["baseline"]["evaluator"]]
    for flag, value in flags.items():
        command.extend([flag, value])
    write(original_case / "candidate-execution.json", {
        "command": command, "execution_mode": "bulk_contended", "returncode": 0, "after": {}})
    observed = []

    def validate(report, m, assignment, side, *, historical_output=None):
        observed.append((side, historical_output))
        return report["results"][0]

    runner.validate_report = validate
    before = {path: sha(path) for path in original.rglob("*.json")}
    result = collector.summarize(manifest_path, runner_path, output)
    assert ("baseline", original_output) in observed
    assert result["statuses"]["baseline"] == {"absent": 1, "complete": 1}
    assert result["statuses"]["candidate"] == {"complete": 1, "pending": 1}
    assert all(sha(path) == checksum for path, checksum in before.items())
