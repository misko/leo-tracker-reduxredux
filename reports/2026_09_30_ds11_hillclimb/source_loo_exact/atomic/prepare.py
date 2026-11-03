#!/usr/bin/env python3
"""Build the digest-bound index-0 atomic exact source-holdout job plan."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
EXPERIMENT = HERE.parent
HILL = EXPERIMENT.parent
ROOT = HERE.parents[3]
BASE = HILL.parent / "2026_09_30_ds11_single10"
INDEX = 0
FAMILY_ORDER = (
    "iid_t4_scale100",
    "source_receiver_equal",
    "robust_t8_scale100",
    "robust_t4_scale200",
)
FAMILY_VARIANTS = {
    "iid_t4_scale100": "iid",
    "source_receiver_equal": "source_receiver_equal",
    "robust_t8_scale100": "df8",
    "robust_t4_scale200": "scale200",
}
COMPLETED_FAMILIES = ("iid_t4_scale100", "source_receiver_equal")
AUDIT_CACHES = {
    "robust_t8_scale100": (59195, 65512),
    "robust_t4_scale200": (59195, 65512),
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Sources:
    def __init__(self):
        self.rows = {}

    def add(self, path, expected=None):
        path = Path(path).resolve()
        actual = digest(path)
        if expected is not None and actual != expected.removeprefix("sha256:"):
            raise ValueError(f"source hash mismatch: {path}")
        previous = self.rows.get(str(path))
        if previous is not None and previous != actual:
            raise ValueError(f"conflicting source binding: {path}")
        self.rows[str(path)] = actual
        return path

    def add_bound_map(self, rows):
        for path, expected in rows.items():
            self.add(path, expected)


def load_json(path):
    return json.loads(Path(path).read_text())


def validate_receipt(path, *, family, exit_code=0):
    row = load_json(path)
    if row.get("index") != INDEX or row.get("family") != family or row.get("exit_code") != exit_code:
        raise ValueError(f"terminal receipt mismatch: {path}")
    return row


def canonical_context(sources):
    phase_path = sources.add(HILL / "source_loo" / "runs" / "phase1" / "00.json")
    phase_receipt = sources.add(HILL / "source_loo" / "runs" / "phase1" / "00.receipt.json")
    phase = load_json(phase_path)
    receipt = load_json(phase_receipt)
    if (phase.get("schema") != "ds11-source-loo-influence-phase1/v1"
            or phase.get("index") != INDEX or phase.get("reference_used") is not False
            or receipt.get("index") != INDEX or receipt.get("exit_code") != 0):
        raise ValueError("canonical phase-one result is not a qualified terminal index-0 result")
    sources.add_bound_map(phase["sources"])
    counts = Counter(row["norad"] for row in phase["assignments"] if row["unambiguous"])
    norads = sorted(int(norad) for norad, count in counts.items() if count >= 2)
    if norads != phase["eligible_sources"] or len(norads) != 14:
        raise ValueError("canonical eligible source census mismatch")
    groups = {
        norad: [row["track_id"] for row in phase["assignments"]
                if row["unambiguous"] and row["norad"] == norad]
        for norad in norads
    }
    endpoints = {row["family"]: row["endpoint_x"] for row in phase["families"]}
    if tuple(endpoints) != FAMILY_ORDER:
        raise ValueError("canonical family order mismatch")
    plan_path = sources.add(BASE / "plan.json")
    plan = load_json(plan_path)
    entry = plan["inputs"][INDEX]
    if entry["session_id"] != phase["session_id"]:
        raise ValueError("canonical plan session mismatch")
    for artifact in entry["artifacts"]:
        sources.add(artifact["path"], artifact["sha256"])
    return phase, groups, endpoints, plan_path, plan, entry


def validate_family_cache(path, receipt_path, family, phase, groups, endpoint, sources):
    path = sources.add(path)
    receipt_path = sources.add(receipt_path)
    receipt = validate_receipt(receipt_path, family=family)
    if receipt.get("run_sha256") != digest(EXPERIMENT / "run.py"):
        raise ValueError("family cache runner binding mismatch")
    if receipt.get("protocol_sha256") != digest(EXPERIMENT / "PROTOCOL.md"):
        raise ValueError("family cache protocol binding mismatch")
    row = load_json(path)
    if (row.get("schema") != "ds11-source-loo-exact-family/v1"
            or row.get("index") != INDEX or row.get("session_id") != phase["session_id"]
            or row.get("family") != family or row.get("variant") != FAMILY_VARIANTS[family]
            or row.get("reference_used") is not False or row.get("full_endpoint_x") != endpoint
            or row.get("assignments") != phase["assignments"] or not row.get("family_qualified")):
        raise ValueError(f"family cache provenance mismatch: {family}")
    sources.add_bound_map(row["sources"])
    if row["sources"].get(str((HILL / "source_loo" / "exact_audit.py").resolve())) != digest(
        HILL / "source_loo" / "exact_audit.py"
    ):
        raise ValueError("family cache does not bind the frozen common held scorer")
    by_norad = {fold["norad"]: fold for fold in row["folds"]}
    if sorted(by_norad) != sorted(groups):
        raise ValueError("family cache fold coverage mismatch")
    for norad, fold in by_norad.items():
        if (fold["track_ids"] != groups[norad] or not fold["optimizer"]["qualified"]
                or fold["held_observation_count"] <= 0
                or not isinstance(fold.get("common_held_score"), (int, float))):
            raise ValueError(f"invalid cached family fold {family}/{norad}")
    return path, by_norad


def validate_audit_cache(path, receipt_path, family, norad, phase, groups, endpoint, sources):
    path = sources.add(path)
    receipt_path = sources.add(receipt_path)
    validate_receipt(receipt_path, family=family)
    row = load_json(path)
    if (row.get("schema") != "ds11-source-loo-exact-audit/v1"
            or row.get("index") != INDEX or row.get("session_id") != phase["session_id"]
            or row.get("family") != family or row.get("variant") != FAMILY_VARIANTS[family]
            or row.get("norad") != norad or row.get("reference_used") is not False
            or row.get("full_endpoint_x") != endpoint
            or row.get("source_track_ids") != groups[norad]
            or not row["optimizer"]["qualified"]
            or row["exact_common_held"]["held_observation_count"] <= 0
            or not isinstance(row["exact_common_held"].get("score"), (int, float))):
        raise ValueError(f"exact-audit cache provenance mismatch: {family}/{norad}")
    sources.add_bound_map(row["sources"])
    phase_binding = str((HILL / "source_loo" / "runs" / "phase1" / "00.json").resolve())
    if row["sources"].get(phase_binding) != digest(phase_binding):
        raise ValueError("exact-audit cache does not bind canonical assignments")
    scorer_binding = str((HILL / "source_loo" / "exact_audit.py").resolve())
    if row["sources"].get(scorer_binding) != digest(scorer_binding):
        raise ValueError("exact-audit cache does not bind common held scorer")
    return path


def build_plan():
    sources = Sources()
    sources.add(HERE / "prepare.py")
    sources.add(HERE / "PLAN_PROTOCOL.md")
    sources.add(EXPERIMENT / "run.py")
    sources.add(EXPERIMENT / "PROTOCOL.md")
    sources.add(HILL / "source_loo" / "diagnose.py")
    sources.add(HILL / "source_loo" / "exact_audit.py")
    sources.add(HILL / "source_loo" / "PROTOCOL.md")
    sources.add(HILL / "source_loo" / "EXACT_PROTOCOL.md")
    sources.add(HILL / "source_balance" / "model.py")
    sources.add(HILL / "robust" / "model.py")
    sources.add(ROOT / "tools" / "ds7_baseline_adapter.py")
    sources.add(ROOT / "tools" / "ds7_fast_baseline_adapter.py")
    phase, groups, endpoints, plan_path, original_plan, entry = canonical_context(sources)

    family_caches = {}
    for family in COMPLETED_FAMILIES:
        base = EXPERIMENT / "runs" / "pilot" / f"00_{family}"
        family_caches[family] = validate_family_cache(
            base.with_suffix(".json"), base.with_suffix(".receipt.json"), family,
            phase, groups, endpoints[family], sources,
        )
        family_caches[family] = family_caches[family][0]

    audit_caches = {}
    for family, norads in AUDIT_CACHES.items():
        for norad in norads:
            base = HILL / "source_loo" / "runs" / "exact_audit" / f"00_{family}_{norad}"
            audit_caches[(family, norad)] = validate_audit_cache(
                base.with_suffix(".json"), base.with_suffix(".receipt.json"), family, norad,
                phase, groups, endpoints[family], sources,
            )

    incomplete = []
    for family in AUDIT_CACHES:
        receipt_path = EXPERIMENT / "runs" / "pilot" / f"00_{family}.receipt.json"
        receipt = validate_receipt(receipt_path, family=family, exit_code=124)
        sources.add(receipt_path)
        output_path = receipt_path.with_name(receipt_path.name.replace(".receipt.json", ".json"))
        if output_path.exists():
            raise ValueError("timed-out family unexpectedly has an output eligible for reuse")
        incomplete.append({
            "family": family,
            "receipt_path": str(receipt_path.resolve()),
            "exit_code": receipt["exit_code"],
            "interpretation": "incomplete whole-family execution; not a negative fit outcome",
        })

    jobs = []
    for family in FAMILY_ORDER:
        for norad in sorted(groups):
            cache = None
            if family in family_caches:
                cache = {"kind": "family", "path": str(family_caches[family])}
            elif (family, norad) in audit_caches:
                cache = {"kind": "audit", "path": str(audit_caches[(family, norad)])}
            jobs.append({
                "index": INDEX,
                "family": family,
                "variant": FAMILY_VARIANTS[family],
                "norad": norad,
                "source_track_ids": groups[norad],
                "full_endpoint_x": endpoints[family],
                "cache": cache,
            })
    if len(jobs) != 56 or sum(job["cache"] is not None for job in jobs) != 32:
        raise ValueError("atomic job/cache census mismatch")
    if sum(job["cache"] is None for job in jobs) != 24:
        raise ValueError("atomic pending census mismatch")

    return {
        "schema": "ds11-source-loo-atomic-plan/v1",
        "index": INDEX,
        "session_id": phase["session_id"],
        "reference_used": False,
        "family_order": list(FAMILY_ORDER),
        "norad_order": sorted(groups),
        "eligible_source_count": len(groups),
        "job_count": len(jobs),
        "cached_job_count": sum(job["cache"] is not None for job in jobs),
        "pending_job_count": sum(job["cache"] is None for job in jobs),
        "execution": {"unit": "one fold", "cap_s": 90, "max_workers": 3,
                      "blas_threads_per_worker": 1, "starts_per_job": 1,
                      "within_job_retries": 0},
        "selection": {"requires_qualified_jobs": 56,
                      "requires_identical_coverage": True,
                      "score": "sum common original-IID t4/100 held log density over all folds",
                      "tie_order": list(FAMILY_ORDER)},
        "common_held_rule": {
            "model": "original IID Student-t4 scale100",
            "cfo_profile": "training observations only per track and candidate",
            "score": "joint-minus-training log mixture density with same CFO",
            "implementation_path": str((HILL / "source_loo" / "exact_audit.py").resolve()),
            "implementation_sha256": digest(HILL / "source_loo" / "exact_audit.py"),
        },
        "canonical_assignment_path": str((HILL / "source_loo" / "runs" / "phase1" / "00.json").resolve()),
        "canonical_assignment_sha256": digest(HILL / "source_loo" / "runs" / "phase1" / "00.json"),
        "original_plan_path": str(plan_path),
        "original_plan_sha256": digest(plan_path),
        "input_artifacts": entry["artifacts"],
        "preserved_incomplete_family_attempts": incomplete,
        "jobs": jobs,
        "sources": dict(sorted(sources.rows.items())),
    }


def main():
    output = HERE / "plan.json"
    plan = build_plan()
    with output.open("x") as stream:
        json.dump(plan, stream, indent=2, allow_nan=False)
    print(json.dumps({"schema": plan["schema"], "jobs": plan["job_count"],
                      "cached": plan["cached_job_count"], "pending": plan["pending_job_count"],
                      "sources": len(plan["sources"])}))


if __name__ == "__main__":
    main()
