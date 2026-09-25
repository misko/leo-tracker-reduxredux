#!/usr/bin/env python3
"""Add the DS1 surveyed reference only after iteration-28 inference is sealed."""

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
    if seal.read_text().split()[0] != digest(path).split(":", 1)[1]:
        raise ValueError(f"bad seal: {path}")
    return json.loads(path.read_text())


def distance_km(latitude: float, longitude: float) -> float:
    lat1, lat2 = map(math.radians, (REFERENCE[0], latitude))
    dlat = lat2 - lat1
    dlon = math.radians(longitude - REFERENCE[1])
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 6371.0088 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def main() -> None:
    inference_path = HERE / "inference.json"
    qualification_path = HERE / "qualification.json"
    cells_path = HERE / "cells.json"
    inference = verified(inference_path)
    qualification = verified(qualification_path)
    cells = verified(cells_path)
    if (
        inference.get("complete") is not True
        or inference.get("truth_used") is not False
        or inference.get("held_used") is not False
        or qualification.get("inference_digest") != digest(inference_path)
        or qualification.get("qualified") is not False
        or inference.get("estimate") is not None
    ):
        raise ValueError("expected sealed truth-blind no-estimate inference")
    best = min(
        cells["cells"],
        key=lambda row: (row["actual_material_score"], row["coordinate_key"]),
    )
    result = {
        "schema": "ds1-iteration28-basin-search-postseal/v1",
        "reference_role": (
            "introduced only after inference and qualification were sealed; diagnostic only"
        ),
        "reference_coordinate": {
            "latitude_deg": REFERENCE[0],
            "longitude_deg": REFERENCE[1],
        },
        "qualified": False,
        "qualified_estimate": None,
        "sub_km_claim": False,
        "best_visited_cell_diagnostic": {
            "role": "lowest-score visited search point; not an estimate",
            "east_m": best["east_m"],
            "north_m": best["north_m"],
            "latitude_deg": best["latitude_deg"],
            "longitude_deg": best["longitude_deg"],
            "score": best["actual_material_score"],
            "postseal_error_km": distance_km(best["latitude_deg"], best["longitude_deg"]),
        },
        "anchor_postseal_error_km": distance_km(
            *__import__("runpy").run_path(str(HERE / "run.py"))["ANCHOR"]
        ),
        "bindings": {
            "inference": digest(inference_path),
            "qualification": digest(qualification_path),
            "cells": digest(cells_path),
        },
    }
    output = HERE / "evaluation" / "postseal-evaluation.json"
    output.parent.mkdir(exist_ok=True)
    if output.exists() or output.with_suffix(output.suffix + ".sha256").exists():
        raise FileExistsError(output)
    content = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    output.write_text(content)
    output.with_suffix(output.suffix + ".sha256").write_text(
        hashlib.sha256(content.encode()).hexdigest() + "  " + output.name + "\n"
    )


if __name__ == "__main__":
    main()
