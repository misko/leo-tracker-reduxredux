#!/usr/bin/env python3
"""Attach the surveyed DS1 reference after I29 inference and qualification seal."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
REFERENCE = (37.84903264307456, -122.4856541910174)


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def verified(path: Path) -> dict:
    seal = path.with_suffix(path.suffix + ".sha256")
    if not seal.exists() or seal.read_text().split()[0] != digest(path).split(":", 1)[1]:
        raise ValueError(f"bad seal: {path}")
    return json.loads(path.read_text())


def distance_km(latitude: float, longitude: float) -> float:
    lat1, lat2 = map(math.radians, (REFERENCE[0], latitude))
    dlat = lat2 - lat1
    dlon = math.radians(longitude - REFERENCE[1])
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 6371.0088 * math.atan2(math.sqrt(value), math.sqrt(1.0 - value))


def main() -> None:
    inference_path = HERE / "inference.json"
    qualification_path = HERE / "qualification.json"
    inference = verified(inference_path)
    qualification = verified(qualification_path)
    if (
        inference.get("complete") is not True
        or qualification.get("complete") is not True
        or inference.get("truth_used") is not False
        or inference.get("held_used") is not False
        or qualification.get("truth_used") is not False
        or qualification.get("held_used") is not False
        or qualification.get("inference_digest") != digest(inference_path)
    ):
        raise ValueError("sealed reference-free inference and qualification required")
    estimate = inference.get("estimate")
    result = {
        "schema": "ds1-iteration29-resolution-safe-postseal/v1",
        "reference_role": "introduced only after inference and qualification were sealed",
        "reference_coordinate": {"latitude_deg": REFERENCE[0], "longitude_deg": REFERENCE[1]},
        "inference_digest": digest(inference_path),
        "qualification_digest": digest(qualification_path),
        "qualified_before_truth": qualification["qualified"],
        "estimate": None,
        "sub_km": False,
    }
    if estimate is not None:
        error = distance_km(estimate["latitude_deg"], estimate["longitude_deg"])
        result["estimate"] = {**estimate, "postseal_error_km": error}
        result["sub_km"] = qualification["qualified"] and error < 1.0
    output = HERE / "evaluation" / "postseal-evaluation.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() or output.with_suffix(output.suffix + ".sha256").exists():
        raise FileExistsError(output)
    content = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    output.write_text(content)
    output.with_suffix(output.suffix + ".sha256").write_text(
        hashlib.sha256(content.encode()).hexdigest() + "  " + output.name + "\n"
    )


if __name__ == "__main__":
    main()
