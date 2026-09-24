#!/usr/bin/env python3
"""Post-seal evaluation for DS1 iteration 14."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

REFERENCE = (37.84903264307456, -122.4856541910174)


def distance_km(latitude: float, longitude: float) -> float:
    earth = 6371.0088
    lat1, lat2 = map(math.radians, (REFERENCE[0], latitude))
    dlat, dlon = lat2 - lat1, math.radians(longitude - REFERENCE[1])
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * earth * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    inference = json.loads(args.inference.read_text())
    if inference.get("reference_used_for_fit") is not False:
        raise ValueError("inference does not attest the reference boundary")
    winner = inference["winner"]
    result = {
        "schema": "ds1-iteration14-cap800-basin-postseal/v1",
        "inference_sha256": "sha256:" + hashlib.sha256(args.inference.read_bytes()).hexdigest(),
        "reference_role": "introduced only after inference was sealed",
        "reference_coordinate": {"latitude_deg": REFERENCE[0], "longitude_deg": REFERENCE[1]},
        "estimated_position": {
            "latitude_deg": winner["latitude_deg"],
            "longitude_deg": winner["longitude_deg"],
        },
        "postseal_error_km": distance_km(winner["latitude_deg"], winner["longitude_deg"]),
    }
    content = json.dumps(result, indent=2, sort_keys=True) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content)
    args.output.with_suffix(args.output.suffix + ".sha256").write_text(
        hashlib.sha256(content.encode()).hexdigest() + "\n"
    )


if __name__ == "__main__":
    main()
