"""Validate and summarize a frozen full direct-gap cohort without running inference."""

import argparse
import importlib.util
import json
import statistics
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

ARMS = ("c0", "fitted_c")
METRICS = ("gps_error_km", "frequency_score", "residual_rms_hz", "associated_points")
SIDES = ("baseline", "candidate")


def load_runner(path):
    spec = importlib.util.spec_from_file_location("frozen_direct_gap_cohort_runner", path)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    return runner


def validate_manifest(manifest, runner, output):
    historical = manifest.get("historical_baseline_root")
    if manifest["profile"] != "full":
        raise ValueError("A full frozen cohort is required")
    if (manifest["schema_version"] != (5 if historical else 4)
            or manifest["fast_flags"] != runner.FAST_FLAGS):
        raise ValueError("Frozen direct-gap fast policy differs")
    roles = manifest["roles"]
    baseline, candidate = roles["baseline"], roles["candidate"]
    if (baseline["initial"] is not None or candidate["initial"] is not None
            or baseline.get("direct_gap") is not None
            or candidate.get("direct_gap", {}).get("id") != "direct-timing-gap-v1"):
        raise ValueError("Frozen paired role policy differs")
    if not historical and (baseline["source"] != candidate["source"]
                           or baseline["evaluator"] != candidate["evaluator"]
                           or baseline["backend_manifest"] != candidate["backend_manifest"]):
        raise ValueError("Fresh paired source and backend bindings differ")
    members = {m["dataset_label"]: m for m in manifest["members"]}
    if len(members) != len(manifest["members"]) or not members:
        raise ValueError("Frozen members are empty or duplicated")
    assignments = {(a["case"], a["repetition"]): a for a in manifest["schedule"]}
    if (len(assignments) != len(manifest["schedule"])
            or set(a["case"] for a in manifest["schedule"]) != set(members)
            or set(manifest["selection"]["cases"]) != set(members)
            or any(set(a["order"]) != set(SIDES) or len(a["order"]) != 2
                   for a in manifest["schedule"])):
        raise ValueError("Full schedule differs from frozen membership")
    if historical and (manifest["repeats"] != 1 or any(
            a["repetition"] != 0 for a in manifest["schedule"])):
        raise ValueError("Historical controls require one original repetition")
    protected = [manifest["output"], manifest["snapshot"], manifest.get("archive_root"),
                 manifest.get("original_v3_context"), historical,
                 baseline["source"]["root"], candidate["source"]["root"], "/mnt/qnap01"]
    if any(output == Path(root).resolve() or output.is_relative_to(Path(root).resolve())
           or Path(root).resolve().is_relative_to(output)
           for root in protected if root):
        raise ValueError("Collector output overlaps frozen evidence")
    runner.check_bindings(manifest)
    if historical:
        protocol_path = Path(historical) / "protocol.json"
        if manifest["bindings"].get(str(protocol_path)) != runner.sha(protocol_path):
            raise ValueError("Historical protocol is not frozen in the manifest")
        protocol = runner.read(protocol_path)
        if (protocol["snapshot"] != manifest["snapshot"]
                or set(protocol["cases"]) != set(members)
                or protocol["sources"]["candidate"] != baseline["source"]
                or protocol["candidate_limit"] != 0
                or protocol["timeout"] != manifest["timeout"]
                or protocol["references"] != manifest["references"]):
            raise ValueError("Historical control protocol differs")
        for path, checksum in protocol["bindings"].items():
            if path in manifest["bindings"] and manifest["bindings"][path] != checksum:
                raise ValueError(f"Historical frozen binding differs: {path}")
        old_native, new_native = (role["backend_manifest"] for role in (baseline, candidate))
        for key in ("binary", "source", "wrapper"):
            if runner.sha(old_native[key]) != runner.sha(new_native[key]):
                raise ValueError(f"Historical and candidate native {key} differ")
        if runner.sha(old_native["provider"]["path"]) != runner.sha(
                new_native["provider"]["path"]):
            raise ValueError("Historical and candidate native providers differ")
    return members


def worker(manifest, assignment, side, runner, output):
    folder = Path(manifest["output"]) / f"{assignment['case']}-r{assignment['repetition']}"
    historical = side == "baseline" and manifest.get("historical_baseline_root")
    if historical:
        origin = Path(manifest["historical_baseline_root"]) / f"{assignment['case']}-r0"
        execution_path = origin / "candidate-execution.json"
        report_path = origin / "candidate" / "report.json"
    else:
        execution_path = folder / f"{side}-execution.json"
        report_path = folder / side / "report.json"
    if not execution_path.exists():
        if report_path.exists():
            raise ValueError(f"Worker report lacks execution receipt: {report_path}")
        return {"status": "absent", "coverage": False}
    execution = runner.read(execution_path)
    command = execution.get("command", [])
    if historical:
        if execution.get("execution_mode") != "bulk_contended":
            raise ValueError(f"Historical execution mode differs: {execution_path}")
        expected = dict(manifest["fast_flags"])
        expected.update({"--snapshot": manifest["snapshot"], "--cases": assignment["case"],
                         "--profile": "quick", "--version": "algo07v5",
                         "--source-root": manifest["roles"][side]["source"]["root"],
                         "--native-manifest": manifest["roles"][side]["native_manifest"]})
        if manifest["references"]:
            expected["--references"] = manifest["references"]
        if (manifest["roles"][side]["evaluator"] not in command
                or any(command.count(flag) != 1 or command[command.index(flag) + 1] != value
                       for flag, value in expected.items())
                or (not manifest["references"] and "--references" in command)
                or command.count("--output") != 1 or command.count("--timeout") != 1
                or float(command[command.index("--timeout") + 1]) != manifest["timeout"]):
            raise ValueError(f"Historical execution command differs: {execution_path}")
        historical_output = command[command.index("--output") + 1]
    else:
        if (len(command) < 3 or command[:2] != ["taskset", "-c"]
                or command != runner.command(
                    manifest, assignment, side, folder / side, command[2])):
            raise ValueError(f"Execution command differs: {execution_path}")
        historical_output = None
    if "returncode" not in execution or "after" not in execution:
        return {"status": "pending", "coverage": False, "execution_path": str(execution_path)}
    if not report_path.exists():
        return {"status": "failed", "coverage": True,
                "execution_path": str(execution_path),
                "failure": "evaluator_no_report"}
    report = runner.read(report_path)
    row = runner.validate_report(
        report, manifest, assignment, side, historical_output=historical_output
    )
    if row["status"] == "complete" and execution["returncode"] != 0:
        raise ValueError(f"Complete report has failed execution: {execution_path}")
    result = {"status": row["status"], "coverage": True, "report_path": str(report_path),
              "report_sha256": runner.sha(report_path), "execution_path": str(execution_path),
              "execution_sha256": runner.sha(execution_path)}
    if row["status"] != "complete":
        return result
    request_path = Path(row["request_path"])
    request = runner.read(request_path)
    if (request != report["plan"]["jobs"][0]["request"]
            or request["job"]["evaluation_reference"] is not None
            or request["recovery_target_policy"]["maximum_targets"] != 0
            or request.get("direct_gap_policy") != manifest["roles"][side].get("direct_gap")):
        raise ValueError(f"Actual request policy differs: {request_path}")
    receipt_path = (output / "validation" / f"{assignment['case']}-r{assignment['repetition']}"
                    / f"{side}.json")
    role = manifest["roles"][side]
    command = [runner.PYTHON, "-B", str(Path(runner.__file__).resolve()), "inspect",
               "--source-root", role["source"]["root"], "--evaluator", role["evaluator"],
               "--request", str(request_path), "--result-sha256", row["result_sha256"],
               "--report", str(report_path), "--manifest-sha256", runner.digest(manifest),
               "--output", str(receipt_path)]
    subprocess.run(command, env=dict(runner.ENVIRONMENT, PYTHONPATH=role["source"]["root"]),
                   cwd=Path(runner.__file__).parent, check=True)
    work = runner.read(receipt_path)
    if (work["public_store_validated"] is not True
            or work["manifest_sha256"] != runner.digest(manifest)
            or work["report_sha256"] != runner.sha(report_path)
            or work["request_sha256"] != runner.digest(request)
            or work["result_sha256"] != row["result_sha256"]):
        raise ValueError(f"Public validation receipt differs: {receipt_path}")
    if side == "candidate":
        evaluator = runner.evaluator(role["evaluator"])
        store = evaluator.owned_import(
            "leo.storage.localization_v5", role["source"]
        ).LocalizationV5Store
        evidence = store(request["job"]["output_root"]).load(
            request["job"]["identity"]["run_id"]
        )["evidence"]
        gap = evidence["audit"]["gap_recovery"]
        projected = work["direct_gap_recovery"]
        selected = gap["selected"]
        projected_selected = projected["selected"]
        if (gap["policy"] != request["direct_gap_policy"]
                or gap["targets"] != projected["targets"]
                or len(gap["trials"]) != projected["trial_count"]
                or gap["stages"] != projected["stages"]
                or sorted(gap["numerical_receipts"]) != projected["native_receipt_stages"]
                or gap["no_GPS_inference"] is not True
                or gap["causal_only"] is not True
                or (selected is None) != (projected_selected is None)
                or (selected is not None and (
                    selected["track_id"] != projected_selected["track_id"]
                    or selected["branch_id"] != projected_selected["branch_id"]
                    or selected["qualification"]["qualified"]
                    != projected_selected["qualified"]))):
            raise ValueError(f"Direct-gap audit differs from validated publication: {report_path}")
        result["gap"] = gap_summary(gap, projected)
    result.update(arms={arm: {key: row["arms"][arm].get(key) for key in METRICS}
                        for arm in ARMS},
                  owners={arm: row["arms"][arm]["owners"] for arm in ARMS},
                  native_counts=work["native_counts"], validation_path=str(receipt_path),
                  validation_sha256=runner.sha(receipt_path))
    result["c_ablation"] = {
        metric: (result["arms"]["fitted_c"][metric] - result["arms"]["c0"][metric]
                 if result["arms"]["fitted_c"][metric] is not None
                 and result["arms"]["c0"][metric] is not None else None)
        for metric in METRICS
    }
    return result


def gap_summary(gap, projected):
    reasons = Counter()
    for excluded in gap["excluded"]:
        identity = excluded.get("identity", {})
        reason = excluded.get("reason") or identity.get("reason") or identity.get("status")
        if reason is not None:
            reasons[str(reason)] += 1
        if "budget_exhausted" in excluded:
            reasons["budget_exhausted"] += 1
    for trial in gap["trials"]:
        for reason in trial["qualification"].get("reasons", []):
            reasons[str(reason)] += 1
    selected = projected["selected"]
    accepted = (gap["candidate"]["target_ids"] if selected and selected["qualified"] else [])
    if selected and selected["qualified"]:
        outcome = "accepted"
    elif not gap["targets"]:
        outcome = "no_trigger"
    elif any(stage["status"] != "complete" for stage in gap["stages"]) or any(
            "budget_exhausted" in excluded for excluded in gap["excluded"]):
        outcome = "stage_failed"
    elif gap["trials"] and all(
            trial["qualification"]["qualified"] is False for trial in gap["trials"]):
        outcome = "fit_rejected"
    elif any("identity" in excluded for excluded in gap["excluded"]):
        outcome = "identity_rejected"
    else:
        outcome = "inconclusive"
    return {"target_count": len(gap["targets"]), "trial_count": len(gap["trials"]),
            "selected": selected, "qualified": bool(selected and selected["qualified"]),
            "outcome": outcome, "stages": gap["stages"], "excluded": gap["excluded"],
            "trials": gap["trials"],
            "accepted_target_ids": accepted,
            "exclusion_reason_categories": dict(sorted(reasons.items())),
            "inner_stage_seconds": {stage["name"]: stage["seconds"] for stage in gap["stages"]},
            "inner_stage_total_seconds": sum(stage["seconds"] for stage in gap["stages"]),
            "native_receipt_stages": projected["native_receipt_stages"]}


def paired(baseline, candidate):
    result = {"arms": {}, "owner_changes": {}, "native_calls": {
        "baseline": baseline["native_counts"]["calls"],
        "candidate": candidate["native_counts"]["calls"],
        "delta": candidate["native_counts"]["calls"] - baseline["native_counts"]["calls"]}}
    for arm in ARMS:
        result["arms"][arm] = {}
        for metric in METRICS:
            before = baseline["arms"][arm][metric]
            after = candidate["arms"][arm][metric]
            result["arms"][arm][metric] = {"baseline": before, "candidate": after,
                                            "delta": after - before if before is not None
                                            and after is not None else None}
        left, right = baseline["owners"][arm], candidate["owners"][arm]
        added, removed = sorted(right.keys() - left.keys()), sorted(left.keys() - right.keys())
        changed = {key: {"baseline": left[key], "candidate": right[key]}
                   for key in sorted(left.keys() & right.keys()) if left[key] != right[key]}
        accepted_additions = sorted(
            set(added) & set(candidate["gap"]["accepted_target_ids"])
        )
        result["owner_changes"][arm] = {"added": added, "removed": removed,
                                         "identity_changed": changed,
                                         "accepted_additions": accepted_additions}
    return result


def percentile(values, fraction):
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    return ordered[lower] + (ordered[min(lower + 1, len(ordered) - 1)] - ordered[lower]) * (
        position - lower)


def independent_distribution(groups, extractor, *, paired_only=True,
                             position_delta=False):
    values = []
    repetitions = 0
    for group in groups.values():
        measured = [extractor(pair) for row in group for pair in row["repetitions"]
                    if not paired_only or pair["comparison"] is not None]
        measured = [value for value in measured if value is not None]
        if measured:
            values.append(statistics.median(measured))
            repetitions += len(measured)
    result = {"recording_count": len(values), "denominator_recordings": len(groups),
            "measured_repetitions": repetitions,
            "scope": "complete_pairs" if paired_only else "completed_roles",
            "median": statistics.median(values) if values else None,
            "mean": statistics.mean(values) if values else None,
            "minimum": min(values) if values else None,
            "maximum": max(values) if values else None,
            "p90": percentile(values, 0.90) if values else None,
            "p95": percentile(values, 0.95) if values else None}
    if position_delta:
        result.update(tie_threshold_m=1.0,
                      improvement_count=sum(value < -0.001 for value in values),
                      tie_count=sum(abs(value) <= 0.001 for value in values),
                      regression_count=sum(value > 0.001 for value in values))
    return result


def summarize(manifest_path, runner_path, output):
    runner = load_runner(runner_path)
    manifest = runner.read(manifest_path)
    members = validate_manifest(manifest, runner, output)
    output.mkdir(parents=True, exist_ok=True)
    assignments = defaultdict(list)
    for assignment in manifest["schedule"]:
        assignments[assignment["case"]].append(assignment)
    rows, statuses, failures = [], {side: Counter() for side in SIDES}, []
    for case, member in sorted(members.items()):
        repetitions = []
        for assignment in sorted(assignments[case], key=lambda item: item["repetition"]):
            roles = {side: worker(manifest, assignment, side, runner, output) for side in SIDES}
            for side, result in roles.items():
                statuses[side][result["status"]] += 1
                if result["status"] in ("failed", "timed_out"):
                    failures.append({"case": case, "repetition": assignment["repetition"],
                                     "side": side, "status": result["status"],
                                     "reason": result.get("failure")})
            comparison = paired(*[roles[side] for side in SIDES]) if all(
                roles[side]["status"] == "complete" for side in SIDES) else None
            repetitions.append({"repetition": assignment["repetition"],
                                "order": assignment["order"], "roles": roles,
                                "comparison": comparison})
        rows.append({"case": case, "recording_id": member["recording_id"],
                     "availability": member["availability"], "repetitions": repetitions})
    groups = defaultdict(list)
    for row in rows:
        groups[row["recording_id"]].append(row)
    outcomes = Counter()
    for group in groups.values():
        group_outcomes = []
        for row in group:
            for pair in row["repetitions"]:
                candidate = pair["roles"]["candidate"]
                group_outcomes.append(candidate["gap"]["outcome"] if
                                      candidate["status"] == "complete" else "unavailable")
        outcome = group_outcomes[0] if len(set(group_outcomes)) == 1 else "mixed"
        outcomes[outcome] += 1
    expected_pairs = len(manifest["schedule"])
    distributions = {
        arm: {metric: {
            side: independent_distribution(
                groups, lambda pair, a=arm, m=metric, s=side:
                pair["comparison"]["arms"][a][m][s],
                position_delta=(metric == "gps_error_km" and side == "delta"))
            for side in ("baseline", "candidate", "delta")}
            for metric in METRICS}
        for arm in ARMS}
    cost = {name: independent_distribution(
        groups, lambda pair, key=name: (
            pair["comparison"]["native_calls"][key] if key == "delta" else
            pair["roles"][key].get("native_counts", {}).get("calls")),
        paired_only=(name == "delta"))
        for name in ("baseline", "candidate", "delta")}
    cost["inner_stage_total_seconds"] = independent_distribution(
        groups, lambda pair: pair["roles"]["candidate"].get("gap", {}).get(
            "inner_stage_total_seconds"), paired_only=False)
    cost["candidate_native_calls_all_validated"] = independent_distribution(
        groups, lambda pair: pair["roles"]["candidate"].get("native_counts", {}).get(
            "calls"), paired_only=False)
    summary = {"schema_version": 1, "manifest_path": str(manifest_path),
               "manifest_sha256": runner.sha(manifest_path),
               "manifest_digest": runner.digest(manifest),
               "runner_path": str(runner_path), "runner_sha256": runner.sha(runner_path),
               "expected_count": len(rows), "expected_pairs": expected_pairs,
               "independent_recordings": len(groups),
               "candidate_coverage_complete": all(pair["roles"]["candidate"]["coverage"]
                                                  for row in rows for pair in row["repetitions"]),
               "paired_coverage_complete": all(
                   all(role["coverage"] for role in pair["roles"].values())
                   for row in rows for pair in row["repetitions"]),
               "statuses": {side: dict(sorted(counts.items()))
                            for side, counts in statuses.items()},
               "scientific_failures": failures,
               "gap_outcomes_by_recording": dict(sorted(outcomes.items())),
               "accuracy_and_fit_by_recording": distributions,
               "cost_by_recording": cost,
               "timing_scope": "candidate inner direct-gap stages and absolute native calls "
                               "cover every validated complete role; native call deltas cover "
                               "complete pairs only; no worker wall or CPU ratios",
               "members": rows}
    runner.write(output / "summary.json", summary)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = summarize(args.manifest.resolve(), args.runner.resolve(), args.output.resolve())
    print(json.dumps({key: result[key] for key in (
        "expected_count", "candidate_coverage_complete", "paired_coverage_complete", "statuses")}))


if __name__ == "__main__":
    main()
