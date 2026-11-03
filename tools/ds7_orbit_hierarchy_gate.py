#!/usr/bin/env python3
"""Reference-free repeated-candidate audit for the frozen DS7 membership."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

SCHEMA = "ds7-orbit-hierarchy-gate/v1"


def _digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def chronological_groups(plan: dict) -> list[dict]:
    """Return and validate the eleven whole chronological groups."""
    captures = [row["session_id"] for row in plan["captures"]]
    groups = [row for row in plan["units"] if row["kind"] == "group8"]
    flattened = [session for group in groups for session in group["session_ids"]]
    if len(groups) != 11 or any(len(group["session_ids"]) != 8 for group in groups):
        raise ValueError("expected eleven complete groups of eight")
    if flattened != captures or len(set(flattened)) != 88:
        raise ValueError("group8 units do not preserve exact chronological capture membership")
    return groups


def project(session_id: str, payload: dict) -> dict:
    """Discard location diagnostics and retain only declared support evidence."""
    if payload.get("session_id") != session_id:
        raise ValueError(f"tracking response session mismatch for {session_id}")
    product = payload.get("product") or {}
    rows = []
    for candidate in product.get("tle_candidates", []):
        rows.append(
            {
                "physical_group_id": candidate.get("physical_group_id"),
                "leading_catalog_number": candidate.get("leading_catalog_number"),
                "heldout": {
                    "leader_rank": candidate.get("training_leader_heldout_rank"),
                    "leader_persisted": candidate.get("leading_candidate_persisted_on_heldout"),
                    "runner_margin": candidate.get("heldout_runner_negative_log_score_margin"),
                },
                "abstention_recommended": candidate.get("abstention_recommended"),
                "abstention_reasons": candidate.get("abstention_reasons"),
                "candidate_only": candidate.get("candidate_only"),
                "identity_claimed": candidate.get("identity_claimed"),
            }
        )
    return {
        "session_id": session_id,
        "source_digest": product.get("input_manifest_sha256"),
        "product_created_at": product.get("created_at"),
        "product_config_digest": product.get("configuration_digest"),
        "tle_match_config_digest": product.get("tle_match_config_digest"),
        "candidate_only": product.get("candidate_only"),
        "identity_claimed": product.get("identity_claimed"),
        "tle_candidates": rows,
    }


def candidate_supported(row: dict) -> bool:
    held = row.get("heldout", {})
    margin = held.get("runner_margin")
    return (
        row.get("candidate_only") is True
        and row.get("identity_claimed") is False
        and row.get("abstention_recommended") is False
        and row.get("abstention_reasons") == []
        and held.get("leader_persisted") is True
        and held.get("leader_rank") == 1
        and isinstance(margin, (int, float))
        and margin > 0
    )


def audit(plan: dict, projections: list[dict]) -> dict:
    groups = chronological_groups(plan)
    expected = [row["session_id"] for row in plan["captures"]]
    indexed = {row["session_id"]: row for row in projections}
    if list(indexed) != expected:
        raise ValueError("projected membership/order differs from frozen 88")
    membership = {
        session: group["unit_id"] for group in groups for session in group["session_ids"]
    }
    # Fixed before looking at recurrence counts: first five complete chronological
    # groups are donors; the remaining six complete groups are targets.
    donor_ids = {group["unit_id"] for group in groups[:5]}
    target_ids = {group["unit_id"] for group in groups[5:]}
    occurrences: dict[int, list[dict]] = defaultdict(list)
    for projection in projections:
        for row in projection["tle_candidates"]:
            catalog = row.get("leading_catalog_number")
            if isinstance(catalog, int) and candidate_supported(row):
                occurrences[catalog].append(
                    {
                        "session_id": projection["session_id"],
                        "chronological_group": membership[projection["session_id"]],
                        "physical_group_id": row["physical_group_id"],
                    }
                )
    repeats = []
    for catalog, rows in sorted(occurrences.items()):
        donor_groups = sorted({r["chronological_group"] for r in rows} & donor_ids)
        target_groups = sorted({r["chronological_group"] for r in rows} & target_ids)
        if donor_groups and target_groups:
            repeats.append(
                {
                    "leading_catalog_number": catalog,
                    "donor_groups": donor_groups,
                    "target_groups": target_groups,
                    "occurrence_count": len(rows),
                    "status": "candidate_repeat_only",
                }
            )
    identity_rows = [
        row
        for projection in projections
        for row in projection["tle_candidates"]
        if row.get("identity_claimed") is True and row.get("candidate_only") is False
    ]
    admitted = bool(repeats and identity_rows)
    return {
        "schema": SCHEMA,
        "dataset_sha256": plan["dataset_sha256"],
        "plan_content_sha256": plan["content_sha256"],
        "membership": {"expected": 88, "projected": len(projections), "exact": True},
        "donor_target_policy": {
            "declared_split": "first five whole chronological group8 units donate; last six target",
            "donor_groups": sorted(donor_ids),
            "target_groups": sorted(target_ids),
            "within_group_leakage_allowed": False,
        },
        "support_policy": {
            "candidate_repeat": (
                "same leading catalog number in supported rows on both sides of split"
            ),
            "supported_row": "held leader rank 1, persisted, positive runner margin, no abstention",
            "identity_or_calibration_admission": (
                "requires independent asserted identity "
                "(identity_claimed true and candidate_only false); "
                "leading-candidate recurrence alone is insufficient"
            ),
        },
        "candidate_repeat_count": len(repeats),
        "candidate_repeats": repeats,
        "independently_asserted_identity_row_count": len(identity_rows),
        "qualifying_identity_or_calibration_prior_count": 0 if not admitted else len(repeats),
        "gate": {
            "status": "pass" if admitted else "stop",
            "variant_fit_admitted": admitted,
            "reason": (
                "independent identity support exists across separated groups"
                if admitted
                else (
                    "candidate recurrences do not establish independently supported "
                    "satellite identity or calibration"
                )
            ),
        },
        "projection_digest": _digest(projections),
        "projections": projections,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8090/api/v1/scanner/tracking")
    parser.add_argument("--request-timeout", type=float, default=3.0)
    parser.add_argument("--metadata-budget", type=float, default=90.0)
    args = parser.parse_args()
    if not 0 < args.request_timeout <= 3 or not 0 < args.metadata_budget <= 90:
        raise SystemExit("request timeout must be <=3s and metadata budget <=90s")
    plan = json.loads(args.plan.read_text())
    chronological_groups(plan)
    started = time.monotonic()
    projections = []
    for capture in plan["captures"]:
        if time.monotonic() - started >= args.metadata_budget:
            raise SystemExit("metadata budget exhausted before exact membership completed")
        session = capture["session_id"]
        url = args.base_url.rstrip("/") + "/" + session
        with urllib.request.urlopen(url, timeout=args.request_timeout) as response:
            projections.append(project(session, json.load(response)))
        source_digest = projections[-1]["source_digest"]
        if source_digest is not None and source_digest != capture["manifest_sha256"]:
            raise SystemExit(f"source digest mismatch: {session}")
    result = audit(plan, projections)
    result["metadata_retrieval"] = {
        "request_count": len(projections),
        "request_timeout_seconds": args.request_timeout,
        "budget_seconds": args.metadata_budget,
        "elapsed_seconds": time.monotonic() - started,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
