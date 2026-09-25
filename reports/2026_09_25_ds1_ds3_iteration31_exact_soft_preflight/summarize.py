#!/usr/bin/env python3
"""Serialize the sealed, fail-closed iteration-31 conclusion."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLAN = HERE / "paired-plan-v2.json"
RESULT = HERE / "preflight-v2.json"
CANDIDATES = HERE / "candidate-table.json"
INFLUENCE = HERE / "influence-table.json"
ATLAS = HERE / "exact-phase-atlas.json"
OUTPUT = HERE / "findings.json"


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def verified(path: Path) -> dict:
    observed = digest(path).removeprefix("sha256:")
    expected = path.with_suffix(path.suffix + ".sha256").read_text().split()[0]
    if observed != expected.removeprefix("sha256:"):
        raise ValueError(f"bad artifact seal: {path}")
    return json.loads(path.read_text())


def write(path: Path, value: dict) -> None:
    if path.exists() or path.with_suffix(path.suffix + ".sha256").exists():
        raise FileExistsError(path)
    text = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    path.write_text(text)
    path.with_suffix(path.suffix + ".sha256").write_text(
        hashlib.sha256(text.encode()).hexdigest() + "\n"
    )


def main() -> None:
    plan = verified(PLAN)
    result = verified(RESULT)
    verified(CANDIDATES)
    verified(INFLUENCE)
    atlas = verified(ATLAS)
    if result["paired_preflight_passed"] is not False:
        raise ValueError("this conclusion only supports a paired no-go")
    statuses = {}
    for dataset, row in result["datasets"].items():
        statuses[dataset] = {
            "terminal_status": "unqualified_preflight",
            "failed_criteria": [name for name, passed in row["criteria"].items() if not passed],
            "winner_cell_id": row["influence_summary"]["full_winner_cell_id"],
            "temperature_hz": row["candidate_summary"]["temperature_hz"],
            "temperature_interior": row["candidate_summary"]["temperature_interior"],
        }
    document = {
        "schema": "paired-ds1-ds3-iteration31-findings/v1",
        "complete": True,
        "truth_used": False,
        "held_used": False,
        "paired_terminal_status": "unqualified_preflight",
        "full_geographic_search_run": False,
        "bindings": {
            "plan": digest(PLAN),
            "preflight": digest(RESULT),
            "candidates": digest(CANDIDATES),
            "influence": digest(INFLUENCE),
            "exact_phase_atlas": digest(ATLAS),
        },
        "dataset_statuses": statuses,
        "exact_state_coverage": {
            dataset: {
                "receipt_bound_state_records": len(records),
                "candidate_session_observations": sum(row["observation_count"] for row in records),
            }
            for dataset, records in atlas["datasets"].items()
        },
        "worked": [
            (
                "both arms built and used receipt-bound exact SGP4 state nodes for every "
                "proposal candidate"
            ),
            (
                "both temperatures selected an interior 400 Hz value on the expanded "
                "25--1600 Hz grid"
            ),
            "both bounded surfaces were finite and bitwise repeatable",
            "the scale-aware DS3 deformation gate passed",
        ],
        "failed": [
            "DS1 left five of twelve leave-one-session reruns with a different local winner",
            "DS1 maximum normalized source-deletion surface deformation was 2.3184, above 1.0",
            "DS3 had three of twenty-three source deletions change its local winner",
        ],
        "learned": [
            (
                "the prior upper-edge temperature failure was model misspecification: exact "
                "candidate rate states yield an interior predictive optimum"
            ),
            (
                "exact per-candidate rate treatment does not yet make the DS1 48.8 m local "
                "direction stable"
            ),
            (
                "the remaining DS1 instability is distributed across several sources rather "
                "than being isolated to NORAD 66961"
            ),
            (
                "a one-session DS3 preflight can test source deletion but cannot define "
                "leave-one-session stability"
            ),
        ],
        "next": [
            "diagnose source sets by predictive influence before changing the sealed source gate",
            "use multiple independently selected DS3 sessions for a second paired preflight",
            (
                "only seal a geographic search after both dataset arms pass their respective "
                "stability gates"
            ),
        ],
        "plan_method": plan["method"]["name"],
        "elapsed_s": result["elapsed_s"],
    }
    write(OUTPUT, document)


if __name__ == "__main__":
    main()
