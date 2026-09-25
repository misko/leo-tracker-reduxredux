#!/usr/bin/env python3
"""Evaluate sealed iteration-32 inference against a separately supplied reference."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import tempfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
INFERENCE = HERE / "inference.json"
QUALIFICATION = HERE / "qualification.json"


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def verify(path: Path) -> dict[str, Any]:
    expected = digest(path).removeprefix("sha256:")
    seal = path.with_suffix(path.suffix + ".sha256")
    if not seal.is_file() or seal.read_text().split()[0].removeprefix("sha256:") != expected:
        raise ValueError(f"unsealed artifact: {path}")
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(path)
    return value


def write_sealed(path: Path, value: dict[str, Any]) -> None:
    if path.exists() or path.with_suffix(path.suffix + ".sha256").exists():
        raise FileExistsError(path)
    text = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as handle:
        handle.write(text)
        temporary = Path(handle.name)
    temporary.replace(path)
    path.with_suffix(path.suffix + ".sha256").write_text(
        hashlib.sha256(text.encode()).hexdigest() + "\n"
    )


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    return 2.0 * radius_km * math.asin(math.sqrt(a))


def evaluate(reference_latitude: float, reference_longitude: float, output: Path) -> dict[str, Any]:
    inference = verify(INFERENCE)
    qualification = verify(QUALIFICATION)
    if qualification.get("bindings", {}).get("inference") != digest(INFERENCE):
        raise ValueError("qualification is not bound to inference")
    winner = inference["winner"]
    value = {
        "schema": "ds3-iteration32-session-nominal-postseal/v1",
        "complete": True,
        "bindings": {
            "inference": digest(INFERENCE),
            "qualification": digest(QUALIFICATION),
        },
        "qualification": {
            "qualified": qualification["qualified"],
            "terminal_status": qualification["terminal_status"],
        },
        "estimated_position": {
            "latitude_deg": winner["latitude_deg"],
            "longitude_deg": winner["longitude_deg"],
        },
        "reference_coordinate": {
            "latitude_deg": reference_latitude,
            "longitude_deg": reference_longitude,
        },
        "postseal_error_km": haversine_km(
            winner["latitude_deg"],
            winner["longitude_deg"],
            reference_latitude,
            reference_longitude,
        ),
        "reference_used_for_inference": False,
        "held_observations_used": False,
    }
    if output.exists():
        existing = verify(output)
        if existing != value:
            raise ValueError("post-seal evaluation already exists with different content")
        return existing
    write_sealed(output, value)
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-latitude", type=float, required=True)
    parser.add_argument("--reference-longitude", type=float, required=True)
    parser.add_argument("--output", type=Path, default=HERE / "postseal-evaluation.json")
    args = parser.parse_args()
    evaluate(args.reference_latitude, args.reference_longitude, args.output)


if __name__ == "__main__":
    main()
