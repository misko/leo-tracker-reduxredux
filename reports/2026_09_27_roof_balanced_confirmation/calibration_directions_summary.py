"""Summarize the frozen robust-vs-original calibration direction movement."""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
LOCATION = HERE.parent / "2026_09_27_roof_location_geometry"


def digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def aggregate(rows: list[dict]) -> dict:
    tracks = defaultdict(list)
    for row in rows:
        tracks[(row["session_id"], row["track_id"])].append(row)
    values = []
    for key, group in tracks.items():
        de = np.asarray([row["delta_east"] for row in group], float)
        du = np.asarray([row["delta_up"] for row in group], float)
        values.append({
            "key": key, "weight": float(group[0]["weight_seconds"]),
            "map_changed": bool(group[0]["map_changed"]),
            "mean_delta_east": float(np.mean(de)),
            "mean_delta_up": float(np.mean(du)),
            "mean_absolute_delta_east": float(np.mean(np.abs(de))),
            "mean_absolute_delta_up": float(np.mean(np.abs(du))),
            "mean_east_up_movement": float(np.mean(np.hypot(de, du))),
            "mean_track_max_east_up_movement": float(np.max(np.hypot(de, du))),
        })
    if not values:
        raise ValueError("empty group")
    weight = np.asarray([value["weight"] for value in values], float)
    fields = [name for name in values[0] if name not in ("key", "weight", "map_changed")]
    delta_east = np.asarray([row["delta_east"] for row in rows], float)
    delta_up = np.asarray([row["delta_up"] for row in rows], float)
    return {
        "tracks": len(values), "reception_rows": len(rows),
        "occupied_second_weight": float(weight.sum()),
        "observation_equal": {
            "mean_delta_east": float(np.mean(delta_east)),
            "mean_delta_up": float(np.mean(delta_up)),
            "mean_absolute_delta_east": float(np.mean(np.abs(delta_east))),
            "mean_absolute_delta_up": float(np.mean(np.abs(delta_up))),
            "mean_east_up_movement": float(np.mean(np.hypot(delta_east, delta_up))),
            "max_east_up_movement": float(np.max(np.hypot(delta_east, delta_up))),
        },
        "track_equal": {name: float(np.mean([value[name] for value in values]))
                        for name in fields},
        "occupied_second_weighted": {
            name: float(np.average([value[name] for value in values], weights=weight))
            for name in fields},
    }


def main() -> None:
    data_path = HERE / "calibration_directions_data.json"
    data_bytes = data_path.read_bytes()
    data = json.loads(data_bytes)
    fixed_path = LOCATION / "topology_frequency_fixedpoint.json"
    fixed_bytes = fixed_path.read_bytes()
    parameters_path = LOCATION / "topology_frequency_parameters.json"
    parameter_bytes = parameters_path.read_bytes()
    parameters = json.loads(parameter_bytes)
    if (parameters["extraction_sha256"] != digest(fixed_bytes) or
            parameters["parameters"]["scale_hz"] != data["frozen_parameters"]["scale_hz"] or
            parameters["parameters"]["degrees_of_freedom"] !=
            data["frozen_parameters"]["degrees_of_freedom"] or
            not parameters["converged"]):
        raise ValueError("direction artifact does not bind the frozen parameter pair")
    rows = data["rows"]
    track_keys = {(row["session_id"], row["track_id"]) for row in rows}
    if len(track_keys) != 344:
        raise ValueError(f"expected 344 retained tracks, got {len(track_keys)}")

    # A shared candidate is an internal timing/coordinate oracle: the old
    # association stored az/el propagated at tau=0 and the new bank position
    # is independently converted to east/up at that exact observation index.
    differences = []
    comparisons = 0
    for row in rows:
        old = {value["candidate_id"]: value for value in row["old_candidates"]}
        for new in row["robust_candidates"]:
            previous = old.get(new["candidate_id"])
            if previous is not None:
                differences.extend((abs(new["east"] - previous["east"]),
                                    abs(new["up"] - previous["up"])))
                comparisons += 1
    if not comparisons:
        raise ValueError("no shared candidates to validate tau=0 directions")
    max_difference = max(differences)
    if max_difference > 2e-12:
        raise ValueError(f"old/new shared-candidate direction mismatch: {max_difference}")

    changed = [row for row in rows if row["map_changed"]]
    unchanged = [row for row in rows if not row["map_changed"]]
    output = {
        "scope": "Calibration-only direction movement from original Gaussian top-3 weights/components to the frozen topology robust Student-t top-3 weights/components; no refit or evaluation locations.",
        "source_hashes": {
            "calibration_directions_data": digest(data_bytes),
            "topology_frequency_fixedpoint": digest(fixed_bytes),
            "topology_frequency_parameters": digest(parameter_bytes),
            "summary_code": digest(Path(__file__).read_bytes()),
        },
        "binding_checks": {
            "frozen_parameter_extraction_hash_matches": True,
            "frozen_parameter_values_match": True,
            "frozen_parameter_converged": True,
            "retained_track_count": 344,
            "shared_candidate_direction_comparisons": comparisons,
            "shared_candidate_east_up_max_absolute_difference": max_difference,
            "shared_candidate_tau_seconds": 0.0,
        },
        "definitions": {
            "movement": "Per reception observation, hypot(robust_mean_east-old_mean_east, robust_mean_up-old_mean_up).",
            "observation_equal": "Every reception row has weight one; reported because dense tracks contribute more under this descriptive view.",
            "track_equal": "First average observations within each track, then give every track weight one.",
            "occupied_second_weighted": "First average observations within each track, then weight tracks by frozen weight_seconds.",
        },
        "all": aggregate(rows),
        "map_changed": aggregate(changed),
        "map_unchanged": aggregate(unchanged),
    }
    target = HERE / "calibration_directions_summary.json"
    if target.exists():
        raise FileExistsError(f"refusing to overwrite {target}")
    target.write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
