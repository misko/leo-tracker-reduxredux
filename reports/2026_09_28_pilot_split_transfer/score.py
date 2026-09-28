"""Replay archived pilot matrices and aggregate paired window diagnostics."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
from ds789_pilot_split import evaluate_frame  # noqa: E402


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compare(a, b):
    if isinstance(a, dict):
        assert a.keys() == b.keys()
        for k in a:
            compare(a[k], b[k])
    elif isinstance(a, list):
        assert len(a) == len(b)
        for x, y in zip(a, b, strict=True):
            compare(x, y)
    elif isinstance(a, float):
        assert np.isclose(a, b, rtol=1e-9, atol=1e-8), (a, b)
    else:
        assert a == b, (a, b)


rows, windows, frames = [], [], 0
for dataset in ("DS7", "DS8", "DS9"):
    target = HERE / dataset
    for launch in target.glob("*-launch.json"):
        for path, sha in json.loads(launch.read_text())["sha256"].items():
            assert digest(ROOT / path) == sha, path
    if not (target / "result.json").exists():
        rows.append({"dataset": dataset, "state": "unavailable"})
        continue
    result = json.loads((target / "result.json").read_text())
    assert digest(target / "spec.json") == result["spec_sha256"]
    assert digest(target / "matrices.npz") == result["matrices_sha256"]
    spec = json.loads((target / "spec.json").read_text())
    assert digest(ROOT / spec["baseline_path"]) == spec["baseline_sha256"]
    archive = np.load(target / "matrices.npz", allow_pickle=False)
    selected = []
    for window in result["windows"]:
        for frame in window["frames"]:
            replay = evaluate_frame(
                archive[frame["matrix_key"]], archive["times_s"], seed=frame["seed"]
            )
            compare(
                replay,
                {k: v for k, v in frame.items() if k not in ("matrix_key", "seed", "frame_start")},
            )
            frames += 1
        for method in ("ordinary", "robust"):
            fits = [
                next(m for m in f["methods"] if m["method"] == method) for f in window["frames"]
            ]
            if not fits:
                continue
            shifts = [s for m in fits for s in m["injections"]]
            eligible = [s for s in shifts if s["expected_within_bounds"]]
            row = {
                "dataset": dataset,
                "receiver": window["receiver_id"],
                "visit": window["visit_index"],
                "method": method,
                "frames": len(fits),
                "baseline_coherence": float(
                    np.mean([f["baseline_held_coherence"] for f in window["frames"]])
                ),
                "held_coherence": float(np.mean([m["held_coherence"] for m in fits])),
                "scrambled_coherence": float(np.mean([m["scrambled_coherence"] for m in fits])),
                "boundary_frames": sum(m["fit"]["search_boundary"] for m in fits),
                "max_abs_residual_cfo_hz": max(abs(m["fit"]["frequency_hz"]) for m in fits),
                "injection_count": len(shifts),
                "in_bounds_injection_count": len(eligible),
                "in_bounds_injection_boundaries": sum(s["boundary"] for s in eligible),
                "max_abs_in_bounds_shift_error_hz": max(
                    (abs(s["shift_error_hz"]) for s in eligible), default=None
                ),
            }
            row["paired_held_gain"] = row["held_coherence"] - row["baseline_coherence"]
            windows.append(row)
            selected.append(row)
    for method in ("ordinary", "robust"):
        subset = [w for w in selected if w["method"] == method]
        if not subset:
            rows.append({"dataset": dataset, "method": method, "state": "no_frames"})
            continue
        row = {
            "dataset": dataset,
            "method": method,
            "state": "returned",
            "windows": len(subset),
            "frames": sum(w["frames"] for w in subset),
            "equal_window_held_gain": float(np.mean([w["paired_held_gain"] for w in subset])),
            "positive_windows": sum(w["paired_held_gain"] > 0 for w in subset),
            "boundary_frames": sum(w["boundary_frames"] for w in subset),
            "in_bounds_injection_boundaries": sum(
                w["in_bounds_injection_boundaries"] for w in subset
            ),
            "max_abs_in_bounds_shift_error_hz": max(
                w["max_abs_in_bounds_shift_error_hz"] for w in subset
            ),
        }
        row["prerequisite_passed"] = (
            len(subset) == 4
            and row["equal_window_held_gain"] > 0
            and row["boundary_frames"] == 0
            and row["in_bounds_injection_boundaries"] == 0
            and row["max_abs_in_bounds_shift_error_hz"] <= 5
        )
        rows.append(row)
with (HERE / "scores.json").open("x") as stream:
    json.dump({"rows": rows, "windows": windows, "replayed_frames": frames}, stream, indent=2)
print(json.dumps({"rows": rows, "replayed_frames": frames}, indent=2))
