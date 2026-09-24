#!/usr/bin/env python3
"""Freeze the reference-free DS2 finalist set for the remaining model arms."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PORTABLE = ROOT / "reports/2026_09_24_ds2_portable_evaluation"
DATASET = PORTABLE / "dataset.json"
COARSE = PORTABLE / "inference/joint-all20__equal-weight-joint-rate.json"
STAGE_ONE_INDEX = PORTABLE / "refinement-index.json"
FINE_INDEX = PORTABLE / "fine-refinement-index.json"
SPACING_KM = 0.09765625


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def sealed(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if value.get("reference_used_for_fit") is not False:
        raise ValueError(f"input does not attest the reference boundary: {path}")
    seal = path.with_suffix(".sha256")
    alternate = path.with_suffix(path.suffix + ".sha256")
    if not any(
        item.is_file() and item.read_text().strip() == digest(path).removeprefix("sha256:")
        for item in (seal, alternate)
    ):
        raise ValueError(f"input is not sealed: {path}")
    return value


def rate_stage_paths() -> list[Path]:
    stage_one = json.loads(STAGE_ONE_INDEX.read_text())
    fine = json.loads(FINE_INDEX.read_text())
    stage_one_row = next(
        row for row in stage_one["models"] if row["method"] == "equal-weight-joint-rate"
    )
    fine_row = next(
        row for row in fine["models"] if row["method"] == "equal-weight-joint-rate"
    )
    return [COARSE, Path(stage_one_row["final_artifact"]), Path(fine_row["final_artifact"])]


def exact_finalists(path: Path, stage: str) -> list[dict[str, Any]]:
    document = sealed(path)
    rows = [row for row in document["search_trace"] if row.get("stage") == "exact_rate_finalist"]
    if len(rows) != 2 or not document.get("exact_sgp4_winner_gate", {}).get("passed"):
        raise ValueError(f"unexpected exact finalist stage: {path}")
    return [
        {
            "finalist_id": f"{stage}-{index}",
            "source_stage": stage,
            "source_artifact": str(path.resolve()),
            "source_sha256": digest(path),
            "latitude_deg": float(row["latitude_deg"]),
            "longitude_deg": float(row["longitude_deg"]),
            "tau_s": float(row["tau_s"]),
            "source_exact_objective": float(row["objective"]),
            "source_screening_objective": float(row["screening_objective"]),
        }
        for index, row in enumerate(rows, 1)
    ]


def main() -> None:
    dataset = json.loads(DATASET.read_text())
    if dataset.get("reference_coordinate_present") is not False or len(dataset["sessions"]) != 20:
        raise ValueError("DS2 dataset is not the sealed 20-session reference-free corpus")
    stages = ("coarse", "refined", "fine")
    paths = rate_stage_paths()
    finalists = [
        row
        for stage, path in zip(stages, paths, strict=True)
        for row in exact_finalists(path, stage)
    ]
    fine = sealed(paths[-1])
    centre = fine["estimated_position"]
    plan = {
        "schema": "ds2-missing-models-plan/v1",
        "complete": True,
        "partition": "development",
        "reference_coordinate_present": False,
        "reference_used_for_selection": False,
        "dataset": {"path": str(DATASET.resolve()), "sha256": digest(DATASET)},
        "prior": dataset["prior"],
        "session_ids": [row["session_id"] for row in dataset["sessions"]],
        "session_scale": {
            "scientific_model": "repaired common plus per-session fractional Doppler scale",
            "centre": {
                "latitude_deg": float(centre["latitude_deg"]),
                "longitude_deg": float(centre["longitude_deg"]),
                "tau_s": float(fine["global_tau_s"]),
            },
            "spacing_km": SPACING_KM,
            "lattice": "symmetric 3x3",
            "association_policy": "fixed sealed fine-stage all-session rate-winner identities",
            "source_artifact": str(paths[-1].resolve()),
            "source_sha256": digest(paths[-1]),
        },
        "residual_likelihood": {
            "finalists": finalists,
            "candidate_policy": (
                "the two pre-existing exact-rate finalists from each sealed coarse, refined, "
                "and fine portable stage; no coordinate was added or removed"
            ),
            "association_policy": (
                "reconstruct the original full-observation hard association independently at "
                "each frozen coordinate and tau, then freeze it for exact rate and likelihood fits"
            ),
        },
    }
    content = canonical(plan)
    output = HERE / "plan.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content)
    output.with_suffix(output.suffix + ".sha256").write_text(
        hashlib.sha256(content.encode()).hexdigest() + "\n"
    )
    print(canonical({"sessions": len(plan["session_ids"]), "finalists": len(finalists)}), end="")


if __name__ == "__main__":
    main()
