#!/usr/bin/env python3
"""Introduce the reference only after sealing DS2 missing-model inference."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REFERENCE = (37.84903264307456, -122.4856541910174)


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def distance_km(latitude: float, longitude: float) -> float:
    earth = 6371.0088
    a1, a2 = map(math.radians, (REFERENCE[0], latitude))
    dlat = a2 - a1
    dlon = math.radians(longitude - REFERENCE[1])
    value = math.sin(dlat / 2) ** 2 + math.cos(a1) * math.cos(a2) * math.sin(dlon / 2) ** 2
    return 2 * earth * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def row(name: str, value: dict[str, Any]) -> dict[str, Any]:
    return {
        "method": name,
        "latitude_deg": float(value["latitude_deg"]),
        "longitude_deg": float(value["longitude_deg"]),
        "postseal_error_km": distance_km(value["latitude_deg"], value["longitude_deg"]),
    }


def main() -> None:
    inference_path = HERE / "inference.json"
    inference = json.loads(inference_path.read_text())
    if inference.get("reference_used_for_fit") is not False:
        raise ValueError("inference boundary attestation is absent")
    scale = inference["common_plus_session_scale"]
    robust = inference["robust_residual_likelihood"]
    rows = [
        row("matched-rate-only-local", scale["matched_rate_only_winner"]),
        row("common-plus-session-scale", scale["winner"]),
        row("residual-independent-gaussian", robust["gaussian_winner"]),
        row("residual-ar1-student-t", robust["ar1_student_t_winner"]),
    ]
    result = {
        "schema": "ds2-missing-models-postseal-evaluation/v1",
        "development_evaluation": True,
        "inference": {"path": str(inference_path.resolve()), "sha256": digest(inference_path)},
        "reference_coordinate": {
            "latitude_deg": REFERENCE[0],
            "longitude_deg": REFERENCE[1],
            "role": "introduced only after inference.json was sealed",
        },
        "rows": rows,
        "session_scale_lattice": [
            {
                "east_km": item["east_km"],
                "north_km": item["north_km"],
                "latitude_deg": item["latitude_deg"],
                "longitude_deg": item["longitude_deg"],
                "matched_rate_only_objective": item["matched_rate_only"][
                    "selection_objective"
                ],
                "common_plus_session_scale_objective": item[
                    "common_plus_session_scale"
                ]["selection_objective"],
                "postseal_error_km": distance_km(
                    item["latitude_deg"], item["longitude_deg"]
                ),
            }
            for item in scale["rows"]
        ],
        "residual_finalists": [
            {
                "finalist_id": item["finalist_id"],
                "latitude_deg": item["latitude_deg"],
                "longitude_deg": item["longitude_deg"],
                "gaussian_nll": item["gaussian"]["nll_per_weighted_innovation"],
                "ar1_student_t_nll": item["ar1_student_t"][
                    "nll_per_weighted_innovation"
                ],
                "postseal_error_km": distance_km(
                    item["latitude_deg"], item["longitude_deg"]
                ),
            }
            for item in robust["rows"]
        ],
    }
    content = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    output = HERE / "evaluation.json"
    output.write_text(content)
    output.with_suffix(output.suffix + ".sha256").write_text(
        hashlib.sha256(content.encode()).hexdigest() + "\n"
    )
    print(content, end="")


if __name__ == "__main__":
    main()
