#!/usr/bin/env python3
"""Perform the external, post-seal coordinate comparison for cone inference."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent


def distance_km(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    radius_km = 6371.0088
    lat1, lon1, lat2, lon2 = map(math.radians, (a_lat, a_lon, b_lat, b_lon))
    h = math.sin((lat2 - lat1) / 2) ** 2
    h += math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * radius_km * math.asin(math.sqrt(h))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inference", type=Path, default=HERE / "inference.json")
    parser.add_argument("--reference-latitude-deg", type=float, required=True)
    parser.add_argument("--reference-longitude-deg", type=float, required=True)
    parser.add_argument(
        "--method-prefix",
        default="conditional",
        help="Provenance label for the inferred method in the post-seal artifact.",
    )
    parser.add_argument("--output", type=Path, default=HERE / "postseal-evaluation.json")
    args = parser.parse_args()
    inference = json.loads(args.inference.read_text())
    if (
        inference.get("complete") is not True
        or inference.get("reference_used_for_inference") is not False
    ):
        raise ValueError("inference must be sealed and reference-free")
    rows = []
    for result in inference["results"]:
        baseline = result["baseline"]
        methods = [{"method": f"{args.method_prefix} Doppler baseline", **baseline}]
        methods.extend(
            {
                "method": (
                    f"{args.method_prefix} local fitted cone, {width}\N{DEGREE SIGN} full FOV"
                ),
                **winner,
            }
            for width, winner in result["local_fitted_cone"]["winners"].items()
        )
        for method in methods:
            rows.append(
                {
                    "label": result["label"],
                    "method": method["method"],
                    "latitude_deg": method["latitude_deg"],
                    "longitude_deg": method["longitude_deg"],
                    "horizontal_error_km": distance_km(
                        method["latitude_deg"],
                        method["longitude_deg"],
                        args.reference_latitude_deg,
                        args.reference_longitude_deg,
                    ),
                    "training_capped_loss": method["training_capped_loss"],
                }
            )
    output = {
        "schema": "ds2-lt3d-geometry-cone-postseal-evaluation/v1",
        "inference_sha256": "sha256:" + hashlib.sha256(args.inference.read_bytes()).hexdigest(),
        "reference_entered_after_seal": True,
        "reference_coordinate": {
            "latitude_deg": args.reference_latitude_deg,
            "longitude_deg": args.reference_longitude_deg,
        },
        "results": rows,
    }
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
