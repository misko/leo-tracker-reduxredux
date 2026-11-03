"""Strict structural and finite numeric comparison of native site scores."""
import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent


def compare(expected, actual, path="root"):
    if type(expected) is not type(actual):
        raise ValueError(f"type mismatch: {path}")
    if isinstance(expected, dict):
        if expected.keys() != actual.keys():
            raise ValueError(f"key mismatch: {path}")
        return max((compare(expected[k], actual[k], f"{path}.{k}")
                    for k in expected), default=0.0)
    if isinstance(expected, list):
        if len(expected) != len(actual):
            raise ValueError(f"length mismatch: {path}")
        return max((compare(a, b, f"{path}[{i}]")
                    for i, (a, b) in enumerate(zip(expected, actual))), default=0.0)
    if isinstance(expected, float):
        if not math.isfinite(expected) or not math.isfinite(actual):
            raise ValueError(f"nonfinite: {path}")
        delta = abs(expected - actual)
        if not path.endswith("_hz"):
            if expected != actual:
                raise ValueError(f"exact numeric field mismatch: {path}")
            return 0.0
        if delta > 1e-6:
            raise ValueError(f"numeric mismatch: {path}: {delta}")
        return delta
    if expected != actual:
        raise ValueError(f"value mismatch: {path}")
    return 0.0


def main():
    host = json.loads((HERE / "host-score.json").read_text())
    arm = json.loads((HERE / "arm-score.json").read_text())
    delta = compare(host, arm)
    assert len(arm["points"]) == 2
    assert all(p["matched_tracks"] == 64 and len(p["tracks"]) == 64
               for p in arm["points"])
    timing = json.loads((HERE / "physical-score.time.json").read_text())
    assert timing["exit_code"] == 0
    result = {
        "schema": "leo-corrected-native-arm-location/v1",
        "status": "pass", "workers": 2,
        "points": 2, "tracks_per_point": 64,
        "maximum_absolute_numeric_delta_hz": delta,
        "absolute_tolerance_hz": 1e-6,
        "all_satellite_ids_and_tau_values_equal": True,
        "arm_scores_hz": [p["score_hz"] for p in arm["points"]],
        "timing": timing,
        "output_hashes": {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
                          for name in ("host-score.json", "arm-score.json")},
        "scope": "two fixed sites with host-computed native tracks and saved orbit states",
        "server_equivalence_qualified": False,
        "continuous_realtime_qualified": False,
    }
    (HERE / "comparison.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
