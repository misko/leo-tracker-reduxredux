"""Audit sealed pilot outputs and score all arms, retaining missing results."""

import hashlib
import json
import math
import statistics
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
from ds7_eval import horizontal_error_m  # noqa: E402

plan = json.loads((HERE / "plan.json").read_text())
manifests = dict(
    zip(
        ("DS7", "DS8", "DS9"),
        ("2026_09_27_ds7_post_ds6", "2026_09_28_ds8_post_ds7", "2026_09_28_ds9_post_ds8"),
        strict=True,
    )
)
bindings, rows, geographic_checks, start_checks = {}, [], 0, 0
for member in plan:
    unit = member["unit_id"]
    out = HERE / "results" / unit
    seal = json.loads((out / "fit-seal.json").read_text())
    for name, expected in seal["sha256"].items():
        assert name not in bindings or bindings[name] == expected
        bindings[name] = expected
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    dataset = member["dataset_id"]
    manifest_path = ROOT / "reports" / manifests[dataset] / "manifest.json"
    assert (
        "sha256:" + hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        == member["dataset_sha256"]
    )
    manifest = json.loads(manifest_path.read_text())
    capture = sorted(
        manifest["captures"], key=lambda r: (r["capture_start_utc_ns"], r["session_id"])
    )[0]
    assert capture["session_id"] == member["session_id"]
    pose_path = manifest_path.parent / "pose" / (member["session_id"] + ".json")
    assert (
        "sha256:" + hashlib.sha256(pose_path.read_bytes()).hexdigest()
        == capture["pose_file_sha256"]
    )
    authority = json.loads(pose_path.read_text())["pose_authority"]
    row = {
        "unit_id": unit,
        "session_id": member["session_id"],
        "exit_code": int((HERE / "receipts" / unit / "exit-code.txt").read_text()),
        "pose_path": str(pose_path.relative_to(ROOT)),
        "pose_sha256": capture["pose_file_sha256"],
    }
    for arm in ("baseline", "mixture", "broad_only"):
        path = out / (arm + ".json")
        if not path.exists():
            row[arm] = {"state": "missing", "qualified": False}
            continue
        result = json.loads(path.read_text())
        assert result["unit_id"] == unit
        if arm != "baseline" and result["selected"] is None:
            row[arm] = {"state": "no_successful_start", "qualified": False}
            continue
        if arm != "baseline":
            selected = result["selected"]
            assert selected == max(
                (r for r in result["starts"] if r["success"]), key=lambda r: r["training_log_score"]
            )
            assert len(result["starts"]) == 3
            assert [r["timing_start_s"] for r in result["starts"]] == [0, -2, 2]
            for start in result["starts"]:
                boundary = any(
                    min(abs(v - a), abs(v - b)) < 1e-3
                    for v, (a, b) in zip(start["x"], [(-12, 12), (-12, 12), (-5, 5)], strict=True)
                )
                assert start["boundary_hit"] == boundary
                assert start["qualified"] == (
                    start["success"]
                    and not boundary
                    and max(abs(g) for g in start["gradient"]) <= 0.01
                )
                start_checks += 1
        point = result["estimate"]
        error = horizontal_error_m(
            point["latitude_deg"],
            point["longitude_deg"],
            authority["latitude_deg"],
            authority["longitude_deg"],
        )

        def vector(p):
            lat, lon = np.radians([p["latitude_deg"], p["longitude_deg"]])
            return np.array([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)])

        a, b = vector(point), vector(authority)
        independent = 6371008.8 * math.atan2(float(np.linalg.norm(np.cross(a, b))), float(a @ b))
        assert abs(error - independent) < 1e-4
        geographic_checks += 1
        evaluation = result["evaluation"]
        tracks = evaluation["tracks"]
        assert math.isclose(
            sum(t["held_log_score"] for t in tracks),
            evaluation["held_log_score"],
            abs_tol=1e-8,
            rel_tol=0,
        )
        for track in tracks:
            weights = np.array(track["joint_weights"])
            assert np.isfinite(weights).all() and (weights >= 0).all()
            assert abs(weights.sum() - 1) < 1e-10
            assert np.allclose(weights.sum(axis=1), track["scale_weights"], atol=1e-12, rtol=0)
            assert np.allclose(weights.sum(axis=0), track["candidate_weights"], atol=1e-12, rtol=0)
        qualified = (
            result["original_qualified"] and result["gradient_screen"]
            if arm == "baseline"
            else selected["qualified"]
        )
        summary = {
            "state": "returned",
            "qualified": qualified,
            "horizontal_error_m": error,
            "below_1km": qualified and error < 1000,
            "estimate": point,
            "training_log_score": evaluation["training_log_score"],
            "held_log_score": evaluation["held_log_score"],
            "tracks": len(tracks),
            "held_observations": sum(t["held_observations"] for t in tracks),
            "max_abs_gradient": max(abs(g) for g in evaluation["gradient"]),
        }
        if arm == "baseline":
            summary["original_qualified"] = result["original_qualified"]
            summary["gradient_screen"] = result["gradient_screen"]
        else:
            base = json.loads((out / "baseline.json").read_text())["evaluation"]
            assert [t["track_id"] for t in tracks] == [t["track_id"] for t in base["tracks"]]
            assert [t["held_observations"] for t in tracks] == [
                t["held_observations"] for t in base["tracks"]
            ]
            summary["held_delta_vs_baseline"] = (
                evaluation["held_log_score"] - base["held_log_score"]
            )
            summary["positive_held_tracks"] = sum(
                t["held_log_score"] > b["held_log_score"]
                for t, b in zip(tracks, base["tracks"], strict=True)
            )
            summary["successful_starts"] = sum(r["success"] for r in result["starts"])
            summary["boundary_hit"] = selected["boundary_hit"]
            summary["max_start_position_separation_km"] = max(
                math.dist(a["x"][:2], b["x"][:2])
                for a in result["starts"]
                for b in result["starts"]
            )
        if arm == "mixture":
            summary["mean_broad_weight"] = statistics.mean(t["scale_weights"][1] for t in tracks)
            summary["broad_majority_tracks"] = sum(t["scale_weights"][1] > 0.5 for t in tracks)
        row[arm] = summary
    rows.append(row)
output = {
    "rows": rows,
    "audit": {
        "status": "pass",
        "bindings": len(bindings),
        "geographic_checks": geographic_checks,
        "start_checks": start_checks,
    },
    "scope": "First record per dataset; exposed-site pilot, not dataset distributions.",
}
with (HERE / "scores.json").open("x") as f:
    json.dump(output, f, indent=2, allow_nan=False)
fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), constrained_layout=True)
colors = {"baseline": "#526b91", "mixture": "#278985", "broad_only": "#cf9b3e"}
labels = {
    "baseline": "Baseline: 100 Hz",
    "mixture": "Track mixture: 100 / 1,000 Hz",
    "broad_only": "All tracks: 1,000 Hz",
}
for k, arm in enumerate(colors):
    values = [r[arm].get("horizontal_error_m", float("nan")) / 1000 for r in rows]
    bars = axes[0].bar(
        np.arange(3) + (k - 1) * 0.25, values, width=0.23, color=colors[arm], label=labels[arm]
    )
    for bar, row in zip(bars, rows, strict=True):
        if not row[arm]["qualified"]:
            bar.set_hatch("///")
for k, arm in enumerate(("mixture", "broad_only")):
    values = [
        r[arm].get("held_delta_vs_baseline", float("nan")) / r[arm].get("held_observations", 1)
        for r in rows
    ]
    axes[1].bar(
        np.arange(3) + (k - 0.5) * 0.3, values, width=0.28, color=colors[arm], label=labels[arm]
    )
axes[0].axhline(1, color="black", linestyle=":", linewidth=1)
axes[1].axhline(0, color="black", linewidth=0.8)
axes[0].set_ylabel("Horizontal error (km); hatching = unqualified")
axes[1].set_ylabel("Held gain over baseline (nats / observation)")
for ax in axes:
    ax.set_xticks(np.arange(3), [r["unit_id"] for r in rows])
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), fontsize=8)
fig.suptitle("Whole-track scale pilot: geographic error and held prediction")
fig.savefig(HERE / "pilot.png", dpi=170)
fig.savefig(HERE / "pilot.svg")
print(json.dumps(output, indent=2))
