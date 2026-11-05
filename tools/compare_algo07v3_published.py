"""Compare fresh published outputs and explicitly mapped persisted science.

This is an external oracle reader, never a native-engine dependency. Missing
intermediate audit mappings remain an open gate even if every public PNG agrees.
"""

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path

from check_algo07v3_scan_likelihood import fingerprint
from compare_algo07v3_history import compare_persisted

from leo.contracts.digests import canonical_digest
from leo.storage.fast_graph_position_v6 import FastGraphPositionStoreV6
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
from leo.storage.localization_v3 import LocalizationV3Store

# Each entry names a complete persisted scientific document, with only these
# independently visible legacy bookkeeping fields outside its value comparison.
POLICIES = {
    "initial": (
        "ALGO02",
        "worker/inference/SCAN/fit_radio_noise.json",
        None,
        {
            "case",
            "seconds",
            "noise_mode",
            "noise_features_sha256",
            "source_sha256",
            "physical_prior_previous_tle_path",
            "input_read_paths",
        },
    ),
    "recovery": (
        "ALGO02",
        "worker/inference/SCAN/result.json",
        None,
        {"algorithm", "case", "seconds", "source_sha256"},
    ),
    "history_policy": (
        "ALGO02",
        "worker/inference/SCAN/algo02_result.json",
        None,
        {
            "algorithm",
            "case",
            "seconds",
            "history_sha256",
            "baseline_sha256",
            "engine_sha256",
            "history_forecast_sha256",
        },
    ),
    "cavity_nominations": (
        "ALGO02",
        "worker/inference/family_cavity/SCAN_nominations.json",
        None,
        {"seconds"},
    ),
    "cavity_policy": (
        "ALGO02",
        "worker/inference/family_cavity/position/SCAN.json",
        None,
        {"seconds", "nomination_sha256"},
    ),
    "residual_screen": ("ALGO06", "worker/recovery/screen/SCAN/result.json", "screen", {"seconds"}),
    "additional_position": (
        "ALGO06",
        "worker/recovery/position/SCAN/result.json",
        "recovery",
        {"seconds"},
    ),
}


def exact_persisted(original, candidate, excluded):
    if set(original) != set(candidate) | excluded or set(candidate) & excluded:
        raise ValueError("Unexpected persisted fields; comparison scope must be reviewed")
    compare_persisted(
        {k: v for k, v in original.items() if k not in excluded}, fingerprint(candidate)
    )


def read_export(root, stage, relative):
    folder = root / stage
    descriptor = json.loads((folder / "descriptor.json").read_bytes())
    path = (folder / relative).resolve(strict=True)
    if not path.is_relative_to(folder.resolve()):
        raise ValueError("Reference evidence escaped its export")
    raw = path.read_bytes()
    if "sha256:" + hashlib.sha256(raw).hexdigest() != descriptor["files"][relative]:
        raise ValueError("Reference evidence changed")
    return json.loads(raw), descriptor


def bound_link(path, descriptor, folder, expected=None):
    """Verify a legacy path against its public export, never open that legacy path."""
    relative = str(Path("worker") / Path(path).relative_to(descriptor["source_worker_root"]))
    files = {
        name: sha
        for name, sha in descriptor["files"].items()
        if name == relative or name.startswith(relative + "/")
    }
    if not files:
        raise ValueError("Predictive trial has no bound reference evidence")
    if expected is not None and files != {relative: "sha256:" + expected}:
        raise ValueError("Source receipt differs from its export")
    for name, sha in files.items():
        exported = (folder / name).resolve(strict=True)
        if not exported.is_relative_to(folder.resolve()):
            raise ValueError("Source link escaped export")
        if "sha256:" + hashlib.sha256(exported.read_bytes()).hexdigest() != sha:
            raise ValueError("Source bytes changed")
    return relative


def mapped_predictive(original, descriptor, folder):
    """Map only the known process/file representation; verify discarded file links."""
    original = deepcopy(original)

    def bound_path(path, expected=None):
        return bound_link(path, descriptor, folder, expected)

    if original["selected"] is not None:
        selected = original["selected"]
        bound_path(selected.pop("trial"))
        for path, sha in selected.pop("source_receipts").items():
            bound_path(path, sha)
    for row in original["attempts"]:
        if "numerical_retry" in row:
            retry = row["numerical_retry"]
            if set(retry) != {"original_trial", "retry_trial"}:
                raise ValueError("Unknown retry representation")
            for path in retry.values():
                bound_path(path)
            row["numerical_retry"] = True
    stages = original["stages"]
    if not stages or stages[0]["name"] != "inventory" or stages[0]["status"] != "complete":
        raise ValueError("Separate completed inventory stage required")
    for row in stages:
        if row["status"] == "complete" and row["returncode"] != 0:
            raise ValueError("Completed predictive stage has nonzero exit")
    original["stages"] = [{k: row[k] for k in ("name", "status")} for row in stages[1:]]
    labels = {"job_id", "label", "aliases", "scopes"}
    for row in original["inventory_summary"]:
        if not labels <= row.keys():
            raise ValueError("Unknown inventory identity representation")
        for name in labels:
            del row[name]
    return original


def compare_trigger(original, candidate):
    if set(original) != {"ranking", "selected"}:
        raise ValueError("Unknown reassociation trigger representation")
    expected = dict(
        status="reassociation_targets_ranked",
        ranking=original["ranking"],
        targets=original["selected"],
        recovery_complete=False,
    )
    compare_persisted(expected, fingerprint(candidate))


def mapped_propagation(original, descriptor, folder):
    propagation = deepcopy(original)
    for key in ("catalogue", "input"):
        bound_link(
            propagation.pop(key + "_path"),
            descriptor,
            folder,
            propagation.pop(key + "_sha256"),
        )
    return propagation


def compare_screen_no_admission(original, screens, candidate, descriptor, folder):
    if original["selected"] is not None or original["records"] or original["guards"]:
        raise ValueError("Admitted or guarded proposals require independent screen mappings")
    if set(screens) != set(map(str, original["targets"])):
        raise ValueError("Missing or extra family screen")
    screens = deepcopy(screens)
    for screen in screens.values():
        if set(screen["cavity"]) != {"c0", "fitted_c"}:
            raise ValueError("Matched cavity arms required")
        for arm in screen["cavity"].values():
            # Exact schema comparison below rejects every other additional field.
            del arm["seconds"]
    expected = dict(
        status="reassociation_candidates_screened",
        recovery_complete=False,
        admission=dict(
            status="screened",
            targets=original["targets"],
            catalogue_eligibility=mapped_propagation(
                original["catalogue_eligibility"], descriptor, folder
            ),
            propagation_failures=original["propagation_failures"],
            screens=screens,
            shared={},
            guards={},
            admitted=[],
        ),
    )
    compare_persisted(expected, fingerprint(candidate))


def compare_final_fallback(original, candidate, descriptor, folder):
    """Compare the completed no-proposal branch; accepted-fit mapping stays open."""
    if set(candidate) != {"status", "recovery", "recovery_complete"}:
        raise ValueError("Unknown final checkpoint representation")
    if (
        candidate["status"] != "reassociation_evaluated"
        or candidate["recovery_complete"] is not True
    ):
        raise ValueError("Final checkpoint is incomplete")
    value = candidate["recovery"]
    for row in (original, value):
        if row["selected"] is not None or row["records"] or row["review"]:
            raise ValueError("Accepted or reviewed proposals require independent fit mappings")
        if row["execution_status"] != "complete":
            raise ValueError("Final numerical execution incomplete")
    if value["control_fits"] or value["candidate_fits"]:
        raise ValueError("Unmapped intermediate fits exist")
    original = deepcopy(original)
    original["catalogue_eligibility"] = mapped_propagation(
        original["catalogue_eligibility"], descriptor, folder
    )
    protocol = "worker/recovery/candidate/protocol.json"
    protocol_sha = "sha256:" + original["protocol_sha256"]
    if descriptor["files"][protocol] != protocol_sha:
        raise ValueError("Final protocol receipt differs from export")
    if "sha256:" + hashlib.sha256((folder / protocol).read_bytes()).hexdigest() != protocol_sha:
        raise ValueError("Final protocol bytes changed")
    exact_persisted(
        original,
        {k: v for k, v in value.items() if k not in {"control_fits", "candidate_fits"}},
        {"case", "seconds", "protocol_sha256"},
    )


def compare(args):
    request = json.loads(args.request.read_bytes())
    run_id = request["identity"]["run_id"]
    saved = LocalizationV3Store(request["output_root"]).load(run_id)
    evidence = saved["evidence"]
    if evidence["provenance"]["request_sha256"] != canonical_digest(request):
        raise ValueError("Candidate request binding differs")
    source = FastGraphPositionStoreV6(args.reference)
    jobs = [job for job in source.completed_jobs() if job["run_id"] == run_id]
    if len(jobs) != 1:
        raise ValueError("Exactly one completed reference run required")
    native = source.plot_evidence(jobs[0])
    if jobs[0]["input_sha256"] != request["identity"]["input_sha256"]:
        raise ValueError("Different native GLRT inputs")
    reference = FastStandardAnalysisStore(args.reference_publication)
    candidate = FastStandardAnalysisStore(request["output_root"])
    old, new = reference.detail(run_id), candidate.detail(run_id)
    if old["state"] != "complete" or new["state"] != "complete":
        raise ValueError("Both publications must be complete")
    checks, errors = {}, {}

    def check(name, operation):
        try:
            operation()
        except (ValueError, AssertionError) as error:
            checks[name] = False
            errors[name] = str(error)
        else:
            checks[name] = True

    def same(a, b):
        if a != b:
            raise ValueError("Exact values differ")

    for name in ("observations", "tracks"):
        check(name, lambda name=name: same(native[name], evidence["presentation"][name]))
    # These digests may describe different encodings. Verify each public binding
    # against its own actual input rather than erasing a mismatched hash.
    for name, key in (("observations", "observation_sha256"), ("tracks", "tracks_sha256")):
        public_key = "observations_sha256" if name == "observations" else key
        same(old[public_key], native[key])
        same(new[public_key], canonical_digest(evidence["presentation"][name]))
    same(old["terminal_sha256"], native["terminal_receipt"]["sha256"])
    same(new["terminal_sha256"], saved["sha256"])
    bookkeeping = {
        "terminal_sha256",
        "observations_sha256",
        "tracks_sha256",
        "replay_seconds",
        "implementation_model",
        "artifacts",
    }
    check(
        "public_document",
        lambda: same(
            {k: v for k, v in old.items() if k not in bookkeeping},
            {k: v for k, v in new.items() if k not in bookkeeping},
        ),
    )
    same({row["name"] for row in old["artifacts"]}, set(saved["pngs"]))
    for name, data in saved["pngs"].items():
        check(
            "PNG/" + name, lambda name=name, data=data: same(reference.artifact(run_id, name), data)
        )
        same(candidate.artifact(run_id, name), data)
    for name, method in (("grid", "position_grid"), ("path", "position_path")):
        a, b = getattr(reference, method)(run_id), getattr(candidate, method)(run_id)
        same(a["binding"]["terminal_sha256"], old["terminal_sha256"])
        same(b["binding"]["terminal_sha256"], new["terminal_sha256"])
        check(
            name,
            lambda a=a, b=b: same(
                {k: v for k, v in a.items() if k not in {"binding", "elapsed_seconds"}},
                {k: v for k, v in b.items() if k not in {"binding", "elapsed_seconds"}},
            ),
        )
        if name == "grid":
            check(
                "complete_grid",
                lambda a=a, b=b: same(
                    (a["complete"], a["evaluated_points"], b["complete"], b["evaluated_points"]),
                    (True, 179, True, 179),
                ),
            )
    policies = {}
    for name, (stage, relative, inner, excluded) in POLICIES.items():
        original, descriptor = read_export(args.reference_evidence, stage, relative)
        same(descriptor["input_sha256"], request["identity"]["input_sha256"])
        value = evidence["audit"][name]
        if inner:
            value = value[inner]
        check("policy/" + name, lambda o=original, v=value, e=excluded: exact_persisted(o, v, e))
        policies[name] = dict(stage=stage, file=relative, excluded_bookkeeping=sorted(excluded))
    original, descriptor = read_export(
        args.reference_evidence, "ALGO03", "worker/recovery/decision.json"
    )
    same(descriptor["input_sha256"], request["identity"]["input_sha256"])
    mapped = mapped_predictive(original, descriptor, args.reference_evidence / "ALGO03")
    excluded = {
        "baseline",
        "job_id",
        "limitations",
        "maximum_seconds",
        "policy",
        "production_changed",
        "ranking",
        "seconds",
        "shadow_only",
        "source_support_receipt",
    }
    check(
        "policy/predictive_recovery",
        lambda: exact_persisted(mapped, evidence["audit"]["predictive_recovery"], excluded),
    )
    policies["predictive_recovery"] = dict(
        stage="ALGO03",
        file="worker/recovery/decision.json",
        excluded_bookkeeping=sorted(excluded),
        mapped_fields=[
            "trial/source receipt paths verified",
            "retry paths verified then mapped to boolean",
            "inventory is separate owned stage",
            "stage process accounting",
            "inventory identity labels",
        ],
    )
    for name, relative in (
        ("reassociation_trigger", "worker/recovery/candidate/SCAN/trigger.json"),
        (
            "reassociation_complete",
            "worker/recovery/candidate/SCAN/worker_result.json",
        ),
    ):
        original, descriptor = read_export(args.reference_evidence, "ALGO07", relative)
        same(descriptor["input_sha256"], request["identity"]["input_sha256"])
        if name == "reassociation_trigger":
            check(
                "policy/" + name,
                lambda o=original: compare_trigger(o, evidence["audit"]["reassociation_trigger"]),
            )
        else:
            check(
                "policy/" + name,
                lambda o=original, d=descriptor: compare_final_fallback(
                    o,
                    evidence["audit"]["reassociation_complete"],
                    d,
                    args.reference_evidence / "ALGO07",
                ),
            )
            screens = {}
            for target in original["targets"]:
                file = f"worker/recovery/candidate/SCAN/{target}/screen.json"
                screens[str(target)], _ = read_export(args.reference_evidence, "ALGO07", file)
            check(
                "policy/reassociation_screen",
                lambda o=original, d=descriptor, s=screens: compare_screen_no_admission(
                    o,
                    s,
                    evidence["audit"]["reassociation_screen"],
                    d,
                    args.reference_evidence / "ALGO07",
                ),
            )
            if checks["policy/reassociation_screen"]:
                policies["reassociation_screen"] = dict(
                    stage="ALGO07",
                    file=relative,
                    scope="No-admission family screens",
                    excluded_bookkeeping=["cavity/c0/seconds", "cavity/fitted_c/seconds"],
                    metadata_semantics_qualified=False,
                )
        if checks["policy/" + name]:
            policies[name] = dict(
                stage="ALGO07",
                file=relative,
                scope="Complete ranking" if name.endswith("trigger") else "No-proposal fallback",
                metadata_semantics_qualified=False,
            )
    missing = sorted(set(evidence["audit"]) - set(policies))
    reference_clock = json.loads(args.reference_timing.read_bytes())
    candidate_clock = json.loads(args.candidate_timing.read_bytes())
    if (
        reference_clock["state"] != "completed_unqualified"
        or candidate_clock["status"] != "exited"
        or candidate_clock["returncode"] != 0
        or candidate_clock["worker"]["resumed"]
    ):
        raise ValueError("Fresh completed executions required for timing observations")
    return dict(
        input_bindings={
            name: dict(
                path=str(path), sha256="sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
            )
            for name, path in {
                "request": args.request,
                "reference_timing": args.reference_timing,
                "candidate_timing": args.candidate_timing,
                "comparison_tool": Path(__file__),
                **{
                    "export_" + stage: args.reference_evidence / stage / "descriptor.json"
                    for stage in {row["stage"] for row in policies.values()}
                },
            }.items()
        },
        candidate_scientific_receipt_sha256=saved["sha256"],
        checks=checks,
        errors=errors,
        mapped_policies=policies,
        missing_audit_mappings=missing,
        all_checked_values_exact=all(checks.values()),
        full_intermediate_equivalence=False,
        remaining_gate="Map remaining audits and independently qualify excluded metadata links",
        latency_observations=dict(
            reference_seconds=reference_clock["completed_path_seconds"],
            native_v3_process_seconds=candidate_clock["process_seconds"],
            native_v3_worker_seconds=candidate_clock["worker"]["seconds"],
        ),
        qualified_speedup=None,
        full_dataset_equivalence=False,
        production_modified=False,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "request",
        "reference",
        "reference-publication",
        "reference-evidence",
        "reference-timing",
        "candidate-timing",
        "output",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    result = compare(args)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps(result, indent=2))
    # 2 means checked fields pass but the complete equivalence gate is still open.
    raise SystemExit(2 if result["all_checked_values_exact"] else 1)
