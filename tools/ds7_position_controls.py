#!/usr/bin/env python3
"""Cheap DS7 controls over frozen, independently produced per-recording estimates.

Does not fit Doppler or load the dataset reference. Each input estimate must
already be numerically qualified. Missing/failed estimates cause abstention.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def estimate(request: dict) -> dict:
    result = {"schema": "ds7-response/v1", "unit_id": request["unit"]["unit_id"]}
    method = request["config"]["method"]
    if method not in ("equal", "inverse_rms2", "lowest_rms75"):
        raise ValueError("Unknown aggregation control")
    points = []
    for row in request["inputs"]:
        artifacts = [a for a in row["artifacts"] if a["kind"] == "scan_estimate"]
        if len(artifacts) != 1:
            return {**result, "status": "abstained", "reason": "Need exactly one estimate per scan"}
        data = json.loads(Path(artifacts[0]["path"]).read_text())
        if (
            data.get("schema") != "ds7-scan-estimate/v1"
            or data.get("session_id") != row["session_id"]
            or data.get("manifest_sha256") != row["manifest_sha256"]
        ):
            raise ValueError("Estimate source binding mismatch")
        if (
            data.get("status") != "ok"
            or data.get("converged") is not True
            or data.get("boundary_hit") is not False
        ):
            return {**result, "status": "abstained", "reason": "Unqualified upstream estimate"}
        lat, lon = data["estimate"]["latitude_deg"], data["estimate"]["longitude_deg"]
        if not (
            math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180
        ):
            raise ValueError("Invalid upstream position")
        rms = data.get("rf_rms_hz")
        if method != "equal" and (
            not isinstance(rms, (float, int)) or not math.isfinite(rms) or rms <= 0
        ):
            return {**result, "status": "abstained", "reason": "Positive finite RF RMS required"}
        points.append((row["session_id"], lat, lon, rms))
    if not points:
        raise ValueError("No estimates")
    if method == "lowest_rms75":
        points = sorted(points, key=lambda p: (p[3], p[0]))[: max(1, math.ceil(0.75 * len(points)))]
    weights = [1.0] * len(points)
    if method == "inverse_rms2":
        scale = min(p[3] for p in points)
        weights = [(scale / p[3]) ** 2 for p in points]
    xyz = [0.0, 0.0, 0.0]
    for (_, lat, lon, _), weight in zip(points, weights, strict=True):
        a, b = math.radians(lat), math.radians(lon)
        xyz[0] += weight * math.cos(a) * math.cos(b)
        xyz[1] += weight * math.cos(a) * math.sin(b)
        xyz[2] += weight * math.sin(a)
    if math.sqrt(sum(x * x for x in xyz)) < 1e-12 * sum(weights):
        return {**result, "status": "abstained", "reason": "Ambiguous spherical mean"}
    return {
        **result,
        "status": "ok",
        "converged": True,
        "boundary_hit": False,
        "estimate": {
            "latitude_deg": math.degrees(math.atan2(xyz[2], math.hypot(xyz[0], xyz[1]))),
            "longitude_deg": math.degrees(math.atan2(xyz[1], xyz[0])),
        },
        "diagnostics": {
            "method": method,
            "used_session_ids": [p[0] for p in points],
            "weights": weights,
            "position_mean": "unit_sphere_weighted_mean",
            "qualification": "upstream converged/interior; closed-form aggregate",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--response", type=Path, required=True)
    args = parser.parse_args()
    result = estimate(json.loads(args.request.read_text()))
    with args.response.open("x") as stream:
        json.dump(result, stream, allow_nan=False)


if __name__ == "__main__":
    main()
