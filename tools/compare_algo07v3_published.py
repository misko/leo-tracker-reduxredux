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


def compare_handoff_no_addition(original_input, original_replay, additional, candidate):
    """Map the complete retained incumbent using the bound input and replay.

    The old final-stage replay abbreviates the no-addition reason to 'fallback'.
    Its preceding persisted ALGO06 decision contains the full reason retained
    by v3. Compare that document too; do not drop the richer v3 receipt.
    """
    if set(additional["decisions"]) != {"72h_30s"}:
        raise ValueError("Unknown additional policy at reassociation handoff")
    decision = additional["decisions"]["72h_30s"]
    if (
        decision["status"] != "no_qualified_new_family"
        or additional["trials"]
        or additional["control"] is not None
    ):
        raise ValueError("Additional fit branches require independent handoff mappings")
    if set(original_replay) != {"pre_recovery", "recovery", "rebuilt"}:
        raise ValueError("Unknown reassociation replay fields")
    if original_replay["recovery"] != {"status": "fallback"}:
        raise ValueError("Expected independently recorded no-addition fallback")
    expected = dict(
        arms=original_input["baseline_arms"],
        owners=original_input["baseline_owners"],
        replay=dict(original_replay, recovery=decision),
        status="reassociation_prepared",
        recovery_complete=False,
    )
    compare_persisted(expected, fingerprint(candidate))


def compare_additional_preparation(original_input, inventory, preflight, protocol, candidate):
    """Compare the complete selected-one-family residual preparation boundary."""
    selected = original_input["selected"]
    if selected is None or selected["kind"] != "new_family":
        raise ValueError("Other incumbent kinds require independent preparation mappings")
    if original_input["gap_selected"] is not None:
        raise ValueError("Gap additions require an independent family preparation mapping")
    if set(inventory) != {"fragments", "summary"}:
        raise ValueError("Unknown residual inventory fields")
    if "seconds" not in preflight:
        raise ValueError("Missing original preflight timing field")
    expected = dict(
        status="additional_recovery_prepared",
        inventory=dict(
            inventory,
            targets=original_input["targets"],
            eligible_targets=original_input["eligible_targets"],
        ),
        preflight={k: v for k, v in preflight.items() if k != "seconds"},
        selected_owners=original_input["baseline_owners"],
        families=[protocol["family_prior"]],
        replay_checks=preflight["checks"],
        recovery_complete=False,
    )
    compare_persisted(expected, fingerprint(candidate))


def map_preflight_metadata(receipt, root, request):
    """Bind the original file receipts before mapping its compact native view."""
    retained = {
        "origin_utc_ns",
        "cutoff_utc_ns",
        "regional_center",
        "reference_position_used",
        "candidate_count",
        "previous_count",
        "snapshot_count",
    }
    files = {
        "bank_sha256": "worker/inference/SCAN/bank.npz",
        "latest_tle_sha256": "worker/inference/SCAN/selected.tle",
        "previous_tle_sha256": "worker/inference/causal_prior/SCAN/previous.tle",
    }
    constants = dict(
        radius_km=250.0,
        candidate_filter="regional elevation >= -12deg; no whitelist",
        search_center=request["search_center"],
        search_box_width_km=25.0,
        previous_prior_repair="reject epoch differences under one second",
    )
    epochs = {"latest_max_epoch_utc_ns", "latest_max_collection_utc_ns"}
    if set(receipt) != retained | set(files) | set(constants) | epochs:
        raise ValueError("Unknown preflight metadata fields")
    if any(receipt[k] != v for k, v in constants.items()):
        raise ValueError("Original preparation policy differs from the native request")
    if receipt["regional_center"] != request["screen_center"]:
        raise ValueError("Original screening center differs")
    if any(receipt[k] > receipt["cutoff_utc_ns"] for k in epochs):
        raise ValueError("Original catalogue is not causal")
    folder = root / "ALGO02"
    descriptor = json.loads((folder / "descriptor.json").read_bytes())
    if descriptor["input_sha256"] != request["identity"]["input_sha256"]:
        raise ValueError("Different native input in original preparation")
    for key, relative in files.items():
        bound_link(
            str(Path(descriptor["source_worker_root"]) / Path(relative).relative_to("worker")),
            descriptor,
            folder,
            receipt[key],
        )
    return {k: receipt[k] for k in retained}


def compare_signed_snapshot(reference, candidate, root):
    """Restore only the explicitly persisted node/unchanged-arm boundaries.

    The fixture oracle reads these blocks from JSON, which cannot retain NumPy
    scalar/array types. Every value is independently checked against the bound
    persisted document using the existing lossless array restoration rule.
    Newly computed context, priors and likelihoods remain fingerprint-exact.
    """
    actual = fingerprint(candidate)
    original, _ = read_export(root, "ALGO02", "worker/inference/SCAN/result.json")
    node = original["final_node"]
    if reference["node"] != fingerprint(node):
        raise ValueError("Frozen signed node is not the persisted source node")
    compare_persisted(node, actual["node"], "signed/node")
    actual["node"] = reference["node"]
    if reference["signed"]["accepted"] is False:
        cavity, _ = read_export(root, "ALGO02", "worker/inference/family_cavity/position/SCAN.json")
        arms = cavity["baseline_arms"]
        for parent, key in ((reference, "arms"), (reference["signed"], "policy_arms")):
            if parent[key] != fingerprint(arms):
                raise ValueError("Unchanged signed arms differ from persisted incumbent")
        compare_persisted(arms, actual["arms"], "signed/arms")
        compare_persisted(arms, actual["signed"]["policy_arms"], "signed/policy_arms")
        actual["arms"] = reference["arms"]
        actual["signed"]["policy_arms"] = reference["signed"]["policy_arms"]
    if reference != actual:
        raise ValueError("Complete signed context differs after lossless persisted restoration")


def compare_reconstructed_oracle(candidate, path, root, identities, *, signed=False):
    """Verify a frozen reconstruction's input/source bindings and every field."""
    raw = path.read_bytes()
    receipt = json.loads(path.with_suffix(".receipt.json").read_bytes())
    folder = (root / "ALGO02").resolve(strict=True)
    descriptor = json.loads((folder / "descriptor.json").read_bytes())
    if Path(receipt["source"]).resolve() != folder / "worker/inference/SCAN":
        raise ValueError("Oracle reconstructed a different reference export")
    if Path(receipt["output"]["path"]).resolve() != path.resolve():
        raise ValueError("Oracle output path differs")
    if hashlib.sha256(raw).hexdigest() != receipt["output"]["sha256"]:
        raise ValueError("Oracle output changed")
    if "scan_identities" in receipt and receipt["scan_identities"] != identities:
        raise ValueError("Oracle scan identities differ")
    if not receipt["inputs"] or not receipt["modules"]:
        raise ValueError("Complete oracle input/source bindings required")
    for binding in receipt["inputs"]:
        actual = Path(binding["path"]).resolve(strict=True)
        relative = str(actual.relative_to(folder))
        digest = hashlib.sha256(actual.read_bytes()).hexdigest()
        if digest != binding["sha256"] or descriptor["files"].get(relative) != "sha256:" + digest:
            raise ValueError("Oracle input is not bound to the reference export")
    for binding in [receipt["tool"], *receipt["modules"].values()]:
        if hashlib.sha256(Path(binding["path"]).read_bytes()).hexdigest() != binding["sha256"]:
            raise ValueError("Oracle numerical source changed")
    if signed:
        compare_signed_snapshot(json.loads(raw), candidate, root)
    elif json.loads(raw) != fingerprint(candidate):
        raise ValueError("Complete reconstructed oracle differs")


def compare_gap_no_split(original, candidate, descriptor, folder):
    """Verify the complete prepare-only branch using its original native supports."""
    if original["selected"] is not None or original["candidate"] is not None:
        raise ValueError("Selected gap branches require independent fit mappings")
    if original["trials"] or original["excluded"]:
        raise ValueError("Fitted or excluded gap branches require independent mappings")
    mapped = deepcopy(original)
    targets, stages = [], []
    for i, stage in enumerate(original["stages"]):
        if set(stage) != {"command", "returncode", "seconds", "timeout_s"}:
            raise ValueError("Unknown gap process receipt")
        command = stage["command"]
        if (
            len(command) != 6
            or command[1] != "-B"
            or command[3] != "prepare"
            or not command[2].endswith("/algo05_gap_stage.py")
            or stage["returncode"] != 0
        ):
            raise ValueError("Completed gap preparation required")
        source_relative = bound_link(command[4], descriptor, folder)
        source = json.loads((folder / source_relative).read_bytes())
        if set(source) != {"track_id", "points", "inventory", "validation"}:
            raise ValueError("Unknown gap source representation")
        for key in ("inventory", "validation"):
            bound_link(source[key], descriptor, folder)
        prepared_relative = bound_link(command[5], descriptor, folder)
        prepared = folder / prepared_relative
        protocol = json.loads((prepared / "protocol.json").read_bytes())
        for path, sha in protocol["input_sha256"].items():
            bound_link(path, descriptor, folder, sha)
        branches = json.loads((prepared / "branches.json").read_bytes())["branches"]
        parent = protocol["parent_observation_ids"]
        if len(parent) != source["points"] or len(set(parent)) != len(parent):
            raise ValueError("Gap parent support differs")
        if any(
            len(b["observation_ids"]) != len(parent) or set(b["observation_ids"]) != set(parent)
            for b in branches
        ):
            raise ValueError("Actual split branches require independent mappings")
        targets.append({k: source[k] for k in ("track_id", "points")})
        stages.append(
            dict(name=f"gap-{i}-prepare", status="complete", timeout_s=stage["timeout_s"])
        )
    mapped.update(stages=stages, targets=targets, numerical_receipts={})
    actual = deepcopy(candidate)
    for stage in actual["stages"]:
        del stage["seconds"]
    compare_persisted(mapped, fingerprint(actual))


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
    original, descriptor = read_export(
        args.reference_evidence, "ALGO05", "worker/recovery/decision.json"
    )
    same(descriptor["input_sha256"], request["identity"]["input_sha256"])
    check(
        "policy/gap_recovery",
        lambda: compare_gap_no_split(
            original,
            evidence["audit"]["gap_recovery"],
            descriptor,
            args.reference_evidence / "ALGO05",
        ),
    )
    if checks["policy/gap_recovery"]:
        policies["gap_recovery"] = dict(
            stage="ALGO05",
            file="worker/recovery/decision.json",
            scope="Prepare-only branch with unchanged full parent supports",
            metadata_semantics_qualified=False,
        )
    additional_documents = {}
    additional_files = []

    def check_additional_preparation():
        for key, path in (
            ("input", "worker/recovery/inputs/SCAN.json"),
            ("inventory", "worker/recovery/residual-inventory.json"),
            ("preflight", "worker/recovery/preflight/SCAN.json"),
        ):
            value, descriptor = read_export(args.reference_evidence, "ALGO06", path)
            same(descriptor["input_sha256"], request["identity"]["input_sha256"])
            additional_documents[key] = value
            additional_files.append(path)
        selected = additional_documents["input"]["selected"]
        if selected is None or selected["kind"] != "new_family":
            raise ValueError("Other incumbent kinds require independent preparation mappings")
        protocols = [p for p in selected["source_receipts"] if p.endswith("/protocol.json")]
        if len(protocols) != 1:
            raise ValueError("Exactly one bound selected-family protocol required")
        path = protocols[0]
        relative = bound_link(
            path, descriptor, args.reference_evidence / "ALGO06", selected["source_receipts"][path]
        )
        protocol, _ = read_export(args.reference_evidence, "ALGO06", relative)
        additional_files.append(relative)
        preflight = dict(additional_documents["preflight"])
        preflight["scan_receipt"] = map_preflight_metadata(
            preflight["scan_receipt"], args.reference_evidence, request
        )
        compare_additional_preparation(
            additional_documents["input"],
            additional_documents["inventory"],
            preflight,
            protocol,
            evidence["audit"]["additional_recovery"],
        )

    check("policy/additional_recovery", check_additional_preparation)
    if checks["policy/additional_recovery"]:
        policies["additional_recovery"] = dict(
            stage="ALGO06",
            file=additional_files[0],
            supporting_files=additional_files[1:],
            scope="Complete one-family residual preparation; no gap additions",
            excluded_bookkeeping=["preflight/seconds"],
            mapped_metadata=(
                "Original bank/TLE bytes bound; policy constants and causal maxima checked"
            ),
            metadata_semantics_qualified=False,
        )
    handoff_documents = {}
    for key, stage, path in (
        ("input", "ALGO07", "worker/recovery/inputs/SCAN.json"),
        ("replay", "ALGO07", "worker/recovery/candidate/SCAN/replay.json"),
        ("additional", "ALGO06", "worker/recovery/position/SCAN/result.json"),
    ):
        value, descriptor = read_export(args.reference_evidence, stage, path)
        same(descriptor["input_sha256"], request["identity"]["input_sha256"])
        handoff_documents[key] = value
    check(
        "policy/reassociation_handoff",
        lambda: compare_handoff_no_addition(
            handoff_documents["input"],
            handoff_documents["replay"],
            handoff_documents["additional"],
            evidence["audit"]["reassociation_handoff"],
        ),
    )
    if checks["policy/reassociation_handoff"]:
        policies["reassociation_handoff"] = dict(
            stage="ALGO07",
            file="worker/recovery/inputs/SCAN.json",
            supporting_files=[
                "ALGO07/worker/recovery/candidate/SCAN/replay.json",
                "ALGO06/worker/recovery/position/SCAN/result.json",
            ],
            scope="Complete no-addition handoff: both arms, all owners and replay checks",
            mapped_fields=["abbreviated fallback expanded from bound preceding decision"],
            metadata_semantics_qualified=False,
        )
    for name, option in (
        ("signed_policy", "signed_oracle"),
        ("recovery_inventory", "inventory_oracle"),
    ):
        path = getattr(args, option, None)
        if path is None:
            continue
        check(
            "policy/" + name,
            lambda n=name, p=path: compare_reconstructed_oracle(
                evidence["audit"][n],
                p,
                args.reference_evidence,
                request["scan_identities"],
                signed=n == "signed_policy",
            ),
        )
        if checks["policy/" + name]:
            policies[name] = dict(
                stage="ALGO02",
                file="worker/inference/SCAN",
                external_oracle=str(path),
                oracle_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                oracle_receipt_sha256=hashlib.sha256(
                    path.with_suffix(".receipt.json").read_bytes()
                ).hexdigest(),
                scope="Every numerical context field from bound independent frozen reconstruction",
                persisted_type_restoration=(
                    ["node", "unchanged arms", "unchanged signed.policy_arms"]
                    if name == "signed_policy"
                    else []
                ),
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
    parser.add_argument("--signed-oracle", type=Path)
    parser.add_argument("--inventory-oracle", type=Path)
    args = parser.parse_args()
    result = compare(args)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps(result, indent=2))
    # 2 means checked fields pass but the complete equivalence gate is still open.
    raise SystemExit(2 if result["all_checked_values_exact"] else 1)
