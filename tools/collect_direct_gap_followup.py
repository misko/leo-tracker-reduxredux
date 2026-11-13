"""Verify and collect the eight frozen direct-gap follow-up pairs without inference."""

import argparse
import copy
import importlib.util
import json
import statistics
from pathlib import Path
from types import SimpleNamespace

EXPECTED = {
    "ds26-fresh-v2": ("DS26-0263", [("baseline", "candidate")]),
    "ds29-fresh-v2": ("DS29-0126", [("baseline", "candidate")]),
    "ds29-repeat": (
        "DS29-0399",
        [("baseline", "candidate"), ("candidate", "baseline"), ("baseline", "candidate")],
    ),
    "ds26-repeat": (
        "DS26-0002",
        [("baseline", "candidate"), ("candidate", "baseline"), ("baseline", "candidate")],
    ),
}


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def pair_audit(root, case, repetition):
    suffix = f"{case.lower()}-r{repetition}" if case in ("DS29-0399", "DS26-0002") else case.lower()
    return root / f"audit-{suffix}" / "pair-audit.json"


def preflight(root, scope_sha256, runner_path, runner):
    scope_path = root / "scope-receipt-v2.json"
    if runner.sha(scope_path) != scope_sha256:
        raise ValueError("Frozen scope receipt changed")
    scope = runner.read(scope_path)
    if (
        scope["pair_count"] != 8
        or scope["worker_count"] != 16
        or scope["launch_order"] != list(EXPECTED)
        or scope["cpu_affinity"] != "21"
        or scope["blas_threads"] != 1
        or scope["runner"] != {"path": str(runner_path), "sha256": runner.sha(runner_path)}
    ):
        raise ValueError("Follow-up scope differs")
    helper = scope["helper"]
    if runner.sha(helper["path"]) != helper["sha256"]:
        raise ValueError("Frozen archive helper changed")
    assignments = []
    for name, (case, orders) in EXPECTED.items():
        receipt = scope["manifest"][name]
        path = Path(receipt["path"])
        if path != root / "plans" / (name + ".json") or runner.sha(path) != receipt["file_sha256"]:
            raise ValueError("Frozen manifest changed: " + name)
        manifest = runner.read(path)
        if (
            runner.digest(manifest) != receipt["digest"]
            or manifest["schedule"] != receipt["schedule"]
            or manifest["timeout"] != 2400
            or manifest["fast_flags"] != runner.FAST_FLAGS
            or manifest["archive_root"] != receipt["archive"]
            or manifest["output"] != receipt["staging"]
            or manifest["roles"]["baseline"]["source"] != manifest["roles"]["candidate"]["source"]
            or manifest["roles"]["baseline"]["evaluator"]
            != manifest["roles"]["candidate"]["evaluator"]
            or manifest["roles"]["baseline"]["backend_manifest"]
            != manifest["roles"]["candidate"]["backend_manifest"]
            or manifest["roles"]["baseline"].get("direct_gap") is not None
            or manifest["roles"]["candidate"].get("direct_gap", {}).get("id")
            != "direct-timing-gap-v1"
            or manifest["roles"]["baseline"]["initial"] is not None
            or manifest["roles"]["candidate"]["initial"] is not None
        ):
            raise ValueError("Frozen manifest policy differs: " + name)
        expected = [
            dict(case=case, repetition=i, order=list(order)) for i, order in enumerate(orders)
        ]
        if manifest["schedule"] != expected:
            raise ValueError("Frozen case or role order differs: " + name)
        runner.check_bindings(manifest)
        terminal_path = Path(manifest["output"]) / "terminal.json"
        if not terminal_path.exists():
            raise ValueError("Incomplete manifest: " + name)
        terminal = runner.read(terminal_path)
        if (
            terminal["status"] != "complete"
            or terminal["failures"]
            or not terminal["paired_coverage_complete"]
            or not terminal["candidate_coverage_complete"]
        ):
            raise ValueError("Manifest has incomplete or failed workers: " + name)
        for assignment in expected:
            folder = Path(manifest["output"]) / f"{case}-r{assignment['repetition']}"
            audit_path = pair_audit(root, case, assignment["repetition"])
            if not audit_path.exists():
                raise ValueError("Missing pair audit: " + str(audit_path))
            for role in ("baseline", "candidate"):
                report_path = folder / role / "report.json"
                if not report_path.exists():
                    raise ValueError("Missing worker report: " + str(report_path))
                row = runner.read(report_path)["results"][0]
                if row["status"] != "complete" or row["process"]["returncode"] != 0:
                    raise ValueError("Worker did not complete: " + str(report_path))
            assignments.append((name, manifest, assignment, terminal_path, audit_path))
    if len(assignments) != 8:
        raise ValueError("Expected exactly eight pairs")
    return scope, assignments


def collect_pair(root, name, manifest, assignment, terminal_path, audit_path, runner, archive):
    case, repetition = assignment["case"], assignment["repetition"]
    audit = runner.read(audit_path)
    if (
        audit["case"] != case
        or audit["repetition"] != repetition
        or audit["order"] != assignment["order"]
        or audit["manifest_sha256"] != runner.sha(Path(root / "plans" / (name + ".json")))
        or audit["manifest_digest"] != runner.digest(manifest)
        or audit["scope_receipt_sha256"] != runner.sha(root / "scope-receipt-v2.json")
        or not all(audit["binding_checks"].values())
    ):
        raise ValueError("Pair audit binding differs: " + str(audit_path))
    output = Path(manifest["output"]) / f"{case}-r{repetition}"
    roles, requests, owners, gaps = {}, {}, {}, {}
    for role in ("baseline", "candidate"):
        report_path = output / role / "report.json"
        report = runner.read(report_path)
        row = runner.validate_report(report, manifest, assignment, role)
        request_path = Path(row["request_path"])
        request = runner.read(request_path)
        requests[role] = request
        role_plan = manifest["roles"][role]
        if (
            request["job"]["evaluation_reference"] is not None
            or request["recovery_target_policy"]["maximum_targets"] != 0
            or request.get("direct_gap_policy") != role_plan.get("direct_gap")
        ):
            raise ValueError("Actual request policy differs: " + str(request_path))
        work_path = output / (role + "-work.json")
        fresh_path = (
            root / "audit-all-eight" / "revalidated" / f"{case}-r{repetition}" / (role + ".json")
        )
        runner.inspect_publication(
            SimpleNamespace(
                source_root=Path(role_plan["source"]["root"]),
                evaluator=Path(role_plan["evaluator"]),
                request=request_path,
                report=report_path,
                manifest_sha256=runner.digest(manifest),
                result_sha256=row["result_sha256"],
                output=fresh_path,
            )
        )
        if runner.read(fresh_path) != runner.read(work_path):
            raise ValueError("Public work differs from fresh inspection: " + str(work_path))
        execution_path = output / (role + "-execution.json")
        execution = runner.read(execution_path)
        expected_command = runner.command(manifest, assignment, role, output / role, "21")
        archive_receipt = execution.get("archive", {})
        archive_path = Path(manifest["archive_root"]) / f"{case}-r{repetition}" / role
        if (
            execution["command"] != expected_command
            or execution["returncode"] != 0
            or execution["execution_mode"] != "contended"
            or not archive_receipt.get("verified")
            or archive_receipt["destination"] != str(archive_path)
            or not (output / role).is_symlink()
            or (output / role).resolve() != archive_path.resolve()
            or archive.digest(archive.tree_binding(archive_path)) != archive_receipt["tree_sha256"]
        ):
            raise ValueError("Worker execution or archive differs: " + str(execution_path))
        evaluator = runner.evaluator(role_plan["evaluator"])
        store_type = evaluator.owned_import(
            "leo.storage.localization_v5", role_plan["source"]
        ).LocalizationV5Store
        evidence = store_type(request["job"]["output_root"]).load(
            request["job"]["identity"]["run_id"]
        )["evidence"]
        receipts = evidence["provenance"]["native_backend"]["receipts"]
        backend_digest = runner.digest(request["backend_manifest"])
        if not receipts or any(
            receipt["backend_manifest_sha256"] != backend_digest
            or receipt["algorithm"] != role_plan["backend_manifest"]["algorithm"]
            or receipt["provider"] != role_plan["backend_manifest"]["provider"]
            or any(value for key, value in receipt["counts"].items() if key.startswith("fallback_"))
            for receipt in receipts
        ):
            raise ValueError("Native receipt or provider differs: " + str(report_path))
        if (
            runner.digest(receipts) != audit["roles"][role]["native_receipts_digest"]
            or len(receipts) != audit["roles"][role]["native_receipts_count"]
        ):
            raise ValueError("Native receipts differ from pair audit: " + str(report_path))
        gap = evidence["audit"].get("gap_recovery")
        if role == "candidate":
            if gap["policy"] != request["direct_gap_policy"]:
                raise ValueError("Direct-gap public audit differs")
        elif gap is not None and "policy" in gap:
            raise ValueError("Unexpected baseline direct-gap audit")
        gaps[role] = gap
        arms = {
            arm: {
                key: row["arms"][arm][key]
                for key in (
                    "associated_points",
                    "frequency_score",
                    "gps_error_km",
                    "owner_sha256",
                    "residual_rms_hz",
                )
            }
            for arm in ("c0", "fitted_c")
        }
        owners[role] = {arm: row["arms"][arm]["owners"] for arm in ("c0", "fitted_c")}
        stages = {
            event["stage"]: event["seconds"]
            for event in row["stage_events"]
            if event.get("event") == "stage"
        }
        saved = audit["roles"][role]
        actual = dict(
            status=row["status"],
            returncode=row["process"]["returncode"],
            wall_seconds=row["process"]["wall_seconds"],
            cpu_seconds=row["process"]["cpu_seconds"],
            stage_seconds=stages,
            arms=arms,
            native_counts=runner.read(work_path)["native_counts"],
            native_receipts_count=len(receipts),
            native_receipts_digest=runner.digest(receipts),
            native_backend_manifest_digest=backend_digest,
            direct_gap_policy=request.get("direct_gap_policy"),
            inference_reference=request["job"]["evaluation_reference"],
            request_path=str(request_path),
            request_sha256=runner.sha(request_path),
            report_path=str(report_path),
            report_sha256=runner.sha(report_path),
            result_sha256=row["result_sha256"],
            public_work_path=str(work_path),
            public_work_sha256=runner.sha(work_path),
            execution_path=str(execution_path),
            execution_sha256=runner.sha(execution_path),
            archive_path=str(archive_path),
            archive_tree_sha256=archive_receipt["tree_sha256"],
        )
        if actual != saved:
            raise ValueError("Pair audit role differs from raw worker: " + str(report_path))
        roles[role] = actual
    left, right = copy.deepcopy(requests["baseline"]), copy.deepcopy(requests["candidate"])
    for request in (left, right):
        request.pop("schema_version")
        request.pop("direct_gap_policy", None)
        request["job"].pop("identity")
        request["job"].pop("output_root")
    if left != right:
        raise ValueError("Paired requests differ beyond direct policy and run identity")
    changes = {}
    for arm in ("c0", "fitted_c"):
        baseline, candidate = owners["baseline"][arm], owners["candidate"][arm]
        added = set(candidate) - set(baseline)
        changes[arm] = dict(
            baseline=len(baseline),
            candidate=len(candidate),
            maps_equal=baseline == candidate,
            new=len(added),
            removed=len(set(baseline) - set(candidate)),
            changed_existing=sum(
                baseline[key] != candidate[key] for key in baseline.keys() & candidate.keys()
            ),
        )
        if changes[arm] != {
            key: value for key, value in audit["owner_changes"][arm].items() if key in changes[arm]
        }:
            raise ValueError("Owner change differs from pair audit")
        selected = gaps["candidate"]["selected"]
        if (
            selected is not None
            and selected["qualification"]["qualified"]
            and added != set(gaps["candidate"]["candidate"]["target_ids"])
        ):
            raise ValueError("Qualified gap target IDs differ from new owners")
    gap = gaps["candidate"]
    if (
        len(gap["targets"]) != len(audit["gap_outcome"]["targets"])
        or len(gap["trials"]) != audit["gap_outcome"]["trial_count"]
        or (gap["selected"] is None) != (audit["gap_outcome"]["selected"] is None)
    ):
        raise ValueError("Direct-gap trial differs from pair audit")
    if not gap["targets"] and (gap["stages"] or gap["numerical_receipts"]):
        raise ValueError("No-trigger control executed direct numerical work")
    return dict(
        case=case,
        repetition=repetition,
        order=assignment["order"],
        manifest=name,
        manifest_sha256=runner.sha(root / "plans" / (name + ".json")),
        terminal_sha256=runner.sha(terminal_path),
        pair_audit_path=str(audit_path),
        pair_audit_sha256=runner.sha(audit_path),
        roles=roles,
        owner_changes=changes,
        gap_outcome=audit["gap_outcome"],
        candidate_minus_baseline=dict(
            wall_seconds=roles["candidate"]["wall_seconds"] - roles["baseline"]["wall_seconds"],
            cpu_seconds=roles["candidate"]["cpu_seconds"] - roles["baseline"]["cpu_seconds"],
            native_calls=roles["candidate"]["native_counts"]["calls"]
            - roles["baseline"]["native_counts"]["calls"],
        ),
    )


def collect(root, scope_sha256, runner_path):
    runner = module(runner_path, "frozen_direct_gap_runner")
    scope, assignments = preflight(root, scope_sha256, runner_path, runner)
    archive = module(
        runner_path.with_name("initial_discovery_archive.py"), "frozen_direct_gap_archive"
    )
    pairs = [collect_pair(root, *item, runner, archive) for item in assignments]
    if len(pairs) != scope["pair_count"]:
        raise ValueError("Collected pair count differs from frozen scope")
    repeat_summaries = {}
    for case in ("DS29-0399", "DS26-0002"):
        group = [pair for pair in pairs if pair["case"] == case]
        if len(group) != 3:
            raise ValueError("Repeated case missing a pair: " + case)
        for role in ("baseline", "candidate"):
            if any(
                pair["roles"][role]["arms"] != group[0]["roles"][role]["arms"] for pair in group
            ):
                raise ValueError("Scientific output changed across repetitions: " + case)
        times = {}
        for clock in ("wall_seconds", "cpu_seconds"):
            baseline = [pair["roles"]["baseline"][clock] for pair in group]
            candidate = [pair["roles"]["candidate"][clock] for pair in group]
            differences = [right - left for left, right in zip(baseline, candidate, strict=True)]
            times[clock] = dict(
                baseline_total=sum(baseline),
                candidate_total=sum(candidate),
                difference_min=min(differences),
                difference_median=statistics.median(differences),
                difference_max=max(differences),
                difference_total=sum(differences),
                aggregate_ratio=sum(candidate) / sum(baseline),
            )
        repeat_summaries[case] = times
    result = dict(
        schema_version=1,
        scope_receipt_path=str(root / "scope-receipt-v2.json"),
        scope_receipt_sha256=scope_sha256,
        runner_path=str(runner_path),
        runner_sha256=runner.sha(runner_path),
        pair_count=len(pairs),
        worker_count=2 * len(pairs),
        all_worker_statuses_complete=True,
        all_manifest_terminals_complete=True,
        failures=[],
        execution_mode="contended",
        headline_timing_eligible=False,
        original_v3_timing_denominator_separate=True,
        verification=(
            "frozen bindings, actual requests, public store, native receipts, archives, owners"
        ),
        pairs=pairs,
        repeat_summaries=repeat_summaries,
    )
    output = root / "audit-all-eight" / "summary.json"
    runner.write(output, result)
    return output, runner.sha(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--scope-sha256", required=True)
    parser.add_argument("--runner", type=Path, required=True)
    args = parser.parse_args()
    output, checksum = collect(args.root.resolve(), args.scope_sha256, args.runner.resolve())
    print(json.dumps(dict(summary=str(output), sha256=checksum)))


if __name__ == "__main__":
    main()
