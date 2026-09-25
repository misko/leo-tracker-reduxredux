#!/usr/bin/env python3
"""Create sealed fail-closed findings from the paired preflight."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PREFLIGHT = HERE / "preflight-v2.json"
PLAN = HERE / "paired-plan-v2.json"
CANDIDATES = HERE / "candidate-table-v2.json"
INFLUENCE = HERE / "influence-table-v2.json"
OUTPUT = HERE / "findings.json"
FAILURE_V1 = HERE / "failure-v1.json"


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_verified(path: Path) -> dict[str, Any]:
    actual = digest(path).removeprefix("sha256:")
    expected = path.with_suffix(path.suffix + ".sha256").read_text().strip().split()[0]
    if actual != expected.removeprefix("sha256:"):
        raise ValueError(f"seal mismatch: {path}")
    return json.loads(path.read_text())


def write_sealed(path: Path, value: dict[str, Any]) -> None:
    if path.exists() or path.with_suffix(path.suffix + ".sha256").exists():
        raise FileExistsError(path)
    text = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    path.write_text(text)
    path.with_suffix(path.suffix + ".sha256").write_text(
        hashlib.sha256(text.encode()).hexdigest() + "\n"
    )


def main() -> None:
    result = load_verified(PREFLIGHT)
    plan = load_verified(PLAN)
    load_verified(CANDIDATES)
    load_verified(INFLUENCE)
    if result["paired_preflight_passed"] is not False:
        raise ValueError("this summary is only valid for the sealed no-go result")
    statuses = {
        dataset: {
            "terminal_status": (
                "qualified_preflight" if row["preflight_passed"] else "unqualified_preflight"
            ),
            "failed_criteria": [name for name, passed in row["criteria"].items() if not passed],
            "full_geographic_search_run": row["full_geographic_search_run"],
        }
        for dataset, row in result["datasets"].items()
    }
    if any(row["terminal_status"] != "unqualified_preflight" for row in statuses.values()):
        raise ValueError("paired fail-closed status mismatch")
    norad_rows = result["datasets"]["DS1"]["source_66961_entries"]
    norad_summary = {
        "candidate_rows": len(norad_rows),
        "leader_and_retained": sum(
            row["candidates"][0]["candidate_id"] == "66961" and row["candidates"][0]["retained"]
            for row in norad_rows
        ),
        "ambiguous_retained_runner": sum(
            any(
                candidate["candidate_id"] == "66961"
                and candidate["rank"] > 1
                and candidate["retained"]
                for candidate in row["candidates"]
            )
            for row in norad_rows
        ),
        "rejected_candidate_rows": sum(
            any(
                candidate["candidate_id"] == "66961" and not candidate["retained"]
                for candidate in row["candidates"]
            )
            for row in norad_rows
        ),
        "destabilizing_source": False,
        "actual_destabilizing_source": "65351",
    }
    findings = {
        "schema": "paired-ds1-ds3-iteration30-findings/v1",
        "complete": True,
        "truth_used": False,
        "held_used": False,
        "bindings": {
            "plan": digest(PLAN),
            "preflight": digest(PREFLIGHT),
            "candidates": digest(CANDIDATES),
            "influence": digest(INFLUENCE),
        },
        "paired_terminal_status": "unqualified_preflight",
        "dataset_statuses": statuses,
        "full_geographic_search_run": False,
        "worked": [
            "dataset-local all-sky candidate generation completed for both datasets",
            "all coordinate scores were finite and exactly repeatable",
            "DS1 leave-one-session winner agreement was 11/12",
            "DS1 and DS3 leave-one-source winner agreement exceeded 99 percent",
        ],
        "failed": [
            "both datasets exceeded the prospectively sealed absolute source-influence shift gate",
            "temperature selection reached the 400 Hz upper grid edge on both datasets",
            "DS1 fixed soft association reversed the iteration-27 east-west local direction",
        ],
        "learned": [
            "soft association is computationally cheap on the bounded preflight",
            "winner rank is stable although raw score scale is source-sensitive",
            (
                "NORAD 66961 contains one genuinely ambiguous retained case but is not "
                "the influence failure"
            ),
        ],
        "next": [
            (
                "prospectively expand the TRAIN-fold temperature grid until an interior "
                "choice is obtained"
            ),
            (
                "replace raw absolute score-shift acceptance with a predeclared scale-aware "
                "influence diagnostic"
            ),
            (
                "repeat the same paired bounded preflight before any DS3 all56 or broad "
                "geographic search"
            ),
        ],
        "norad_66961": norad_summary,
        "elapsed_s": result["elapsed_s"],
        "plan_method": plan["method"]["name"],
    }
    write_sealed(OUTPUT, findings)
    failure = {
        "schema": "paired-ds1-ds3-iteration30-preflight-failure/v1",
        "terminal_status": "failed_closed_serialization",
        "scientific_result_accepted": False,
        "reason": "sole DS3 session deletion is undefined and was represented as NaN",
        "repair": "v2 reports the one-session deletion diagnostic as explicitly not applicable",
        "bindings": {
            "plan": digest(HERE / "paired-plan.json"),
            "candidate_table": digest(HERE / "candidate-table.json"),
            "preserved_runner": digest(HERE / "run-v1.py"),
        },
    }
    write_sealed(FAILURE_V1, failure)


if __name__ == "__main__":
    main()
