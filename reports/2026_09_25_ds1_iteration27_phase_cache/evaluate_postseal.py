#!/usr/bin/env python3
"""Attach the surveyed DS1 reference only after iteration-27 inference is sealed."""

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
    if (
        path.with_suffix(path.suffix + ".sha256").read_text().split()[0]
        != digest(path).split(":")[1]
    ):
        raise ValueError("bad inference seal")
    return json.loads(path.read_text())


def distance_km(latitude: float, longitude: float) -> float:
    lat1, lat2 = map(math.radians, (REFERENCE[0], latitude))
    dlat = lat2 - lat1
    dlon = math.radians(longitude - REFERENCE[1])
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 6371.0088 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def main() -> None:
    inference_path = HERE / "stencil.json"
    inference = verified(inference_path)
    if (
        inference.get("complete") is not True
        or inference.get("sealed_stencil_run") is not True
        or inference.get("truth_used") is not False
        or inference.get("held_used") is not False
    ):
        raise ValueError("inference was not sealed reference-free")
    winner = next(
        row for row in inference["cells"] if row["cell_id"] == inference["actual_winner_cell_id"]
    )
    center = next(row for row in inference["cells"] if row["east_m"] == 0 and row["north_m"] == 0)
    result = {
        "schema": "ds1-iteration27-phase-cache-postseal/v1",
        "reference_role": "introduced only after smoke and stencil inference were sealed",
        "reference_coordinate": {"latitude_deg": REFERENCE[0], "longitude_deg": REFERENCE[1]},
        "winner": {
            "cell_id": winner["cell_id"],
            "latitude_deg": winner["latitude_deg"],
            "longitude_deg": winner["longitude_deg"],
            "postseal_error_km": distance_km(winner["latitude_deg"], winner["longitude_deg"]),
        },
        "sealed_center_postseal_error_km": distance_km(
            center["latitude_deg"], center["longitude_deg"]
        ),
        "inference_digest": digest(inference_path),
    }
    output = HERE / "evaluation" / "postseal-evaluation.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() or output.with_suffix(".json.sha256").exists():
        raise FileExistsError(output)
    content = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    output.write_text(content)
    output.with_suffix(".json.sha256").write_text(
        hashlib.sha256(content.encode()).hexdigest() + "\n"
    )


if __name__ == "__main__":
    main()
