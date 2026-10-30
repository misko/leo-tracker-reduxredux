"""Publish a v2 envelope only after guarded scientific support replay checks."""

import argparse
import hashlib
import os
import time
from pathlib import Path

from algo03_shadow_worker import ARMS, read, scoped_pair, single_candidate, write
from run_algo03_shadow import check_read_audit
from run_algo03_snapshot import run_snapshot
from stage_algo03_release import MANIFEST, MANIFEST_SHA256

from leo.contracts.fast_graph_position import KIND
from leo.contracts.fast_graph_position_v2 import MODEL_VERSION, RF_CHECKS, validate_terminal
from leo.storage.fast_graph_position import FastGraphPositionStore
from leo.storage.fast_graph_position_v2 import FastGraphPositionStoreV2

ROOT = Path(__file__).resolve().parents[1]


def checked_file(path, recovery):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("Scientific proof may not be a symbolic link")
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(recovery.resolve()):
        raise ValueError("Scientific proof escapes this recovery")
    return resolved


def verify_selected(result, recovery):
    """Read actual replay files and rebuild the exact published candidate."""
    selected = result["selected"]
    if not result["read_audit"]["verified"]:
        raise ValueError("Recovery read audit failed")
    supervisor_pid = result['read_audit'].get('supervisor_process_id', os.getpid())
    roots = [
        read(path)["pid"]
        for path in (recovery / "read_receipts").glob("*.json")
        if read(path)["parent_pid"] == supervisor_pid
    ]
    if (len(roots) != 1
            or result['read_audit'].get('root_process_id', roots[0]) != roots[0]
            or not check_read_audit(recovery, roots[0], supervisor_pid=supervisor_pid)['verified']):
        raise ValueError("Recovery process receipts no longer verify")
    receipts = selected.get("source_receipts", {})
    if not receipts:
        raise ValueError("Missing scientific source receipts")
    for name, expected in receipts.items():
        path = checked_file(name, recovery)
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Scientific proof changed")
    descriptor = read(recovery / "snapshot/descriptor.json")
    inventory = read(
        recovery / "all-large-track-recovery" / descriptor["job_id"] / "inventory.json"
    )
    support_receipts = result.get("source_support_receipt", {})
    if len(support_receipts) != 1:
        raise ValueError("Missing exact baseline ownership replay")
    for name, expected in support_receipts.items():
        path = checked_file(name, recovery)
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Baseline ownership proof changed")
        proof = read(path)
    if proof.get("all_verified") is not True or proof["arms"] != result["source_support"]:
        raise ValueError("Baseline ownership replay disagrees with selected source")
    for name, expected in proof["source_receipts"].items():
        if hashlib.sha256(checked_file(name, recovery).read_bytes()).hexdigest() != expected:
            raise ValueError("Baseline ownership replay source changed")
    inventory["publication_support"] = proof["arms"]
    observations = read(recovery / "snapshot/inference/SCAN/observations.json")
    raw_ids = {o["observation_id"] for o in observations}
    target_ids = {o for t in selected["targets"] for o in t["observation_ids"]}
    if not target_ids <= raw_ids:
        raise ValueError("Scored supports contain a non-original GLRT observation")
    if selected["kind"] != "joint":
        trial = checked_file(Path(selected["trial"]) / "protocol.json", recovery).parent
        proof = read(trial / "exact_owner_replay.json")
        roles = ("control", "target_0" if selected["kind"] == "shared_family" else "new_family")
        if (
            len(proof["rows"]) != 4
            or not proof["all_verified"]
            or {(r["role"], r["arm"]) for r in proof["rows"]}
            != {(r, a) for r in roles for a in ARMS}
            or not all(r["verified"] for r in proof["rows"])
        ):
            raise ValueError("Individual scientific replay is incomplete")
        rebuilt = single_candidate(inventory, trial, selected["kind"] == "shared_family")
    else:
        joint_audits = [
            checked_file(p, recovery)
            for p in receipts
            if Path(p).name == "audit.json" and Path(p).parent.name.startswith("joint-")
        ]
        if len(joint_audits) != 2:
            raise ValueError("Joint scientific replay lacks both c arms")
        joint_root = joint_audits[0].parent.parent
        arms, owners = {}, {}
        for arm in ARMS:
            for method in ("control", "joint"):
                folder = joint_root / (method + "-" + arm)
                audit = read(checked_file(folder / "audit.json", recovery))
                saved = read(checked_file(folder / "result.json", recovery))
                if (
                    not audit["RF_qualified_arm"]
                    or not all(audit["checks"].values())
                    or audit["incumbent_owner_changes"]
                    or not saved["history"][-1]["success"]
                ):
                    raise ValueError("Joint scientific replay does not qualify")
                if method == "joint":
                    arms[arm], owners[arm] = saved, audit["owners"]
        rebuilt = dict(
            kind="joint",
            targets=selected["targets"],
            arms=scoped_pair(inventory, arms, owners, selected["targets"]),
        )
    if rebuilt is None or any(rebuilt[k] != selected[k] for k in ("kind", "targets", "arms")):
        raise ValueError("Published candidate differs from scientific replay")
    for arm in ARMS:
        old = result["source_support"][arm]["owners"]
        if not set(old) <= raw_ids or any(
            selected["arms"][arm]["owners"].get(i) != n for i, n in old.items()
        ):
            raise ValueError("Scientific replay changed original support ownership")
    return dict.fromkeys(RF_CHECKS, True)


def envelope(baseline, result, *, recovery_seconds, proof_checks=None):
    baseline_seconds = baseline["elapsed_seconds"]
    selected = result.get("selected") if proof_checks else None
    decision = result["decision"] if selected else "ALGO02_fallback"
    position = baseline["position"]
    if selected:
        lat, lon = selected["arms"]["fitted_c"]["endpoint_latlon"]
        position = dict(latitude_deg=lat, longitude_deg=lon)
    terminal = dict(
        schema_version=2,
        kind=KIND,
        model_version=MODEL_VERSION,
        input_sha256=baseline["input_sha256"],
        session_id=baseline["session_id"],
        state="complete",
        baseline=baseline,
        selected=selected,
        decision=decision,
        position=position,
        reference_usage="none",
        future_TLE_used=False,
        matched_c_inputs=True,
        selected_arm="fitted_c",
        baseline_seconds=baseline_seconds,
        recovery_seconds=recovery_seconds,
        total_seconds=baseline_seconds + recovery_seconds,
        source_support=result.get("source_support"),
        read_audit=result.get("read_audit"),
        source_support_receipt=result.get("source_support_receipt"),
        rf_checks=proof_checks,
        failure=result.get("failure"),
        recovery_policy=result.get("policy"),
        attempts=result.get("attempts", []),
        stages=result.get("stages", []),
    )
    return validate_terminal(terminal, input_sha256=baseline["input_sha256"])


def run(args):
    preparation_seconds = getattr(args, "preparation_seconds", 0.0)
    if not 0 <= preparation_seconds < args.maximum_seconds:
        raise ValueError("Invalid prior export preparation time")
    began = time.monotonic() - preparation_seconds
    if hashlib.sha256((ROOT / MANIFEST).read_bytes()).hexdigest() != MANIFEST_SHA256:
        raise ValueError("Immutable ALGO03 manifest changed")
    snapshot = getattr(args, "snapshot", None)
    store, job, before = None, None, None
    if snapshot:
        descriptor_path = Path(snapshot)
        if descriptor_path.is_dir():
            descriptor_path /= "descriptor.json"
        descriptor = read(descriptor_path)
        baseline = descriptor["terminal"]
    else:
        store = FastGraphPositionStore(args.bulk_root)
        job = store.status(args.job)
        if not job or job["state"] != "complete":
            raise ValueError("Qualified completed ALGO02 source required")
        FastGraphPositionStoreV2(args.bulk_root, baseline=store).job(job)
        baseline, before = store.terminal(job)
    if baseline["state"] != "complete":
        raise ValueError("Unqualified ALGO02 baseline cannot publish v2 position")
    args.output.mkdir(parents=True, exist_ok=False)
    result, checks = {}, None
    recovery = args.output / "recovery"
    try:
        if not snapshot:
            store.export_analysis(job, args.output / "source-export")
            descriptor_path = args.output / "source-export/descriptor.json"
        result = run_snapshot(descriptor_path, recovery, deadline=began + args.maximum_seconds)
        if result.get("baseline") != baseline:
            raise ValueError("Recovery conditioned on another ALGO02 source")
        if result.get("selected"):
            checks = verify_selected(result, recovery)
    except Exception as error:
        result.update(failure=f"{type(error).__name__}: {error}")
    if store is not None:
        current, after = store.terminal(job)
        if before != after or baseline != current:
            raise ValueError("ALGO02 source terminal changed during recovery")
    terminal = envelope(
        baseline, result, recovery_seconds=time.monotonic() - began, proof_checks=checks
    )
    write(args.output / "terminal.json", terminal)
    return terminal


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--job")
    source.add_argument("--snapshot", type=Path)
    parser.add_argument("--preparation-seconds", type=float, default=0.0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--maximum-seconds", type=int, choices=range(1, 1201), default=1200)
    run(parser.parse_args())
