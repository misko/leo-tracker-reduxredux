"""Post-seal geographic and held comparison with every dataset/arm retained."""

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

bindings = {}
for file in (
    list((HERE / "results").glob("*/*/fit-seal.json"))
    + list((HERE / "bootstrap").glob("*/fit-seal.json"))
    + list((HERE / "curvature").glob("*/seal.json"))
    + list((HERE / "polished").glob("*/*/fit-seal.json"))
):
    for name, sha in json.loads(file.read_text())["sha256"].items():
        assert name not in bindings or bindings[name] == sha
        bindings[name] = sha
for name, sha in bindings.items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == sha, name
plan = json.loads((HERE / "plan.json").read_text())
manifests = {
    "DS7": "2026_09_27_ds7_post_ds6",
    "DS8": "2026_09_28_ds8_post_ds7",
    "DS9": "2026_09_28_ds9_post_ds8",
}
rows = []
geographic_checks = 0
start_checks = 0
polishing_checks = 0
authorities = {}


def error(estimate, authority):
    global geographic_checks
    result = horizontal_error_m(
        estimate["latitude_deg"],
        estimate["longitude_deg"],
        authority["latitude_deg"],
        authority["longitude_deg"],
    )

    def vector(p):
        lat, lon = np.radians([p["latitude_deg"], p["longitude_deg"]])
        return np.array([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)])

    a, b = vector(estimate), vector(authority)
    separate = 6371008.8 * math.atan2(float(np.linalg.norm(np.cross(a, b))), float(a @ b))
    assert abs(result - separate) < 1e-4
    geographic_checks += 1
    return result


for member in plan:
    dataset = member["dataset_id"]
    request = json.loads((ROOT / member["request_path"]).read_text())
    manifest_path = ROOT / "reports" / manifests[dataset] / "manifest.json"
    assert (
        "sha256:" + hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        == request["dataset_sha256"]
    )
    manifest = json.loads(manifest_path.read_text())
    first = sorted(
        manifest["captures"], key=lambda r: (r["capture_start_utc_ns"], r["session_id"])
    )[:8]
    assert (
        [r["session_id"] for r in first] == member["session_ids"] == request["unit"]["session_ids"]
    )
    poses = []
    for capture in first:
        p = manifest_path.parent / "pose" / (capture["session_id"] + ".json")
        assert "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest() == capture["pose_file_sha256"]
        poses.append(json.loads(p.read_text())["pose_authority"])
    assert len({(p["latitude_deg"], p["longitude_deg"]) for p in poses}) == 1
    authority = poses[0]
    authorities[dataset] = authority
    old = json.loads((ROOT / member["response_path"]).read_text())
    row = {
        "dataset_id": dataset,
        "records": 8,
        "historical_joint_error_m": error(old["estimate"], authority),
        "coordinate_origin_error_m": error(
            {
                "latitude_deg": request["config"]["geographic_prior_center_deg"][0],
                "longitude_deg": request["config"]["geographic_prior_center_deg"][1],
            },
            authority,
        ),
    }
    arm_results = {}
    for arm in ("control", "receiver_slope"):
        folder = HERE / "results" / dataset / arm
        path = folder / "result.json"
        if not path.exists():
            row[arm] = {"state": "missing_result", "qualified": False}
            continue
        result = json.loads(path.read_text())
        selected = result["selected"]
        if selected is None:
            row[arm] = {"state": "no_successful_start", "qualified": False}
            continue
        assert result["dataset_id"] == dataset and result["arm"] == arm
        assert selected == max(
            (s for s in result["starts"] if s["success"]), key=lambda s: s["training_log_score"]
        )
        assert [s["timing_start_delta_s"] for s in result["starts"]] == [0, -0.25, 0.25]
        bounds = (
            [(-12, 12)] * 2 + [(-5, 5)] * 8 + ([(-20, 20)] * 2 if arm == "receiver_slope" else [])
        )
        for start in result["starts"]:
            boundary = any(
                min(abs(v - a), abs(v - b)) < 1e-3
                for v, (a, b) in zip(start["x"], bounds, strict=True)
            )
            assert boundary == start["boundary_hit"]
            assert start["qualified"] == (
                start["success"] and not boundary and max(abs(g) for g in start["gradient"]) <= 0.01
            )
            start_checks += 1
        evaluation = result["evaluation"]
        assert [r["session_id"] for r in evaluation] == member["session_ids"]
        assert math.isclose(
            sum(r["training_log_score"] for r in evaluation),
            selected["training_log_score"],
            abs_tol=1e-7,
            rel_tol=0,
        )
        assert math.isclose(
            sum(r["held_log_score"] for r in evaluation),
            result["held_log_score"],
            abs_tol=1e-8,
            rel_tol=0,
        )
        for e in evaluation:
            assert sum(len(g["tracks"]) for g in e["receivers"]) == e["tracks"]
            for group in e["receivers"]:
                assert math.isclose(
                    sum(t["held_log_score"] for t in group["tracks"]),
                    group["held_log_score"],
                    abs_tol=1e-8,
                    rel_tol=0,
                )
                for t in group["tracks"]:
                    assert abs(sum(t["weights"]) - 1) < 1e-10
        distance = error(result["estimate"], authority)
        row[arm] = {
            "state": "returned",
            "qualified": selected["qualified"],
            "horizontal_error_m": distance,
            "below_1km": selected["qualified"] and distance < 1000,
            "estimate": result["estimate"],
            "training_log_score": selected["training_log_score"],
            "held_log_score": result["held_log_score"],
            "held_observations": sum(r["held_observations"] for r in evaluation),
            "tracks": sum(r["tracks"] for r in evaluation),
            "boundary_hit": selected["boundary_hit"],
            "max_abs_gradient": max(abs(g) for g in selected["gradient"]),
            "successful_starts": sum(s["success"] for s in result["starts"]),
            "qualified_starts": sum(s["qualified"] for s in result["starts"]),
            "max_start_position_separation_km": max(
                math.dist(a["x"][:2], b["x"][:2])
                for a in result["starts"]
                for b in result["starts"]
            ),
        }
        if arm == "receiver_slope":
            row[arm]["receiver_slopes_native_hz_s"] = selected["x"][-2:]
        arm_results[arm] = result
    if len(arm_results) == 2:
        a, b = arm_results["control"], arm_results["receiver_slope"]
        deltas = [
            y["held_log_score"] - x["held_log_score"]
            for x, y in zip(a["evaluation"], b["evaluation"], strict=True)
        ]
        assert [e["held_observations"] for e in a["evaluation"]] == [
            e["held_observations"] for e in b["evaluation"]
        ]
        row["paired"] = {
            "geographic_delta_m": row["receiver_slope"]["horizontal_error_m"]
            - row["control"]["horizontal_error_m"],
            "held_log_score_delta": sum(deltas),
            "positive_held_records": sum(d > 0 for d in deltas),
            "held_deltas_by_record": deltas,
            "equal_record_mean_delta_nats_per_observation": statistics.mean(
                d / r["held_observations"] for d, r in zip(deltas, a["evaluation"], strict=True)
            ),
            "both_qualified": row["control"]["qualified"] and row["receiver_slope"]["qualified"],
        }
    refined_results = {}
    row["polished"] = {}
    for arm in ("control", "receiver_slope"):
        path = HERE / "polished" / dataset / arm / "result.json"
        if not path.exists():
            row["polished"][arm] = {"state": "missing_result", "qualified": False}
            continue
        refined = json.loads(path.read_text())
        if refined.get("state") != "returned":
            row["polished"][arm] = {"state": refined["state"], "qualified": False}
            continue
        original = arm_results[arm]["selected"]
        assert refined["original_x"] == original["x"]
        assert refined["original_qualified"] == original["qualified"]
        bounds = (
            [(-12, 12)] * 2 + [(-5, 5)] * 8 + ([(-20, 20)] * 2 if arm == "receiver_slope" else [])
        )
        boundary = any(
            min(abs(v - a), abs(v - b)) < 1e-3
            for v, (a, b) in zip(refined["x"], bounds, strict=True)
        )
        nondecreasing = refined["training_log_score"] >= original["training_log_score"] - 1e-7
        maximum = max(abs(g) for g in refined["gradient"])
        assert (
            refined["boundary_hit"] == boundary
            and refined["training_nondecreasing"] == nondecreasing
        )
        assert refined["qualified"] == (
            refined["success"] and not boundary and maximum <= 0.01 and nondecreasing
        )
        assert math.isclose(
            math.dist(refined["x"][:2], original["x"][:2]) * 1000,
            refined["position_displacement_m"],
            abs_tol=1e-8,
        )
        evaluation = refined["evaluation"]
        assert [e["session_id"] for e in evaluation] == member["session_ids"]
        assert math.isclose(
            sum(e["training_log_score"] for e in evaluation),
            refined["training_log_score"],
            abs_tol=1e-7,
            rel_tol=0,
        )
        assert math.isclose(
            sum(e["held_log_score"] for e in evaluation),
            refined["held_log_score"],
            abs_tol=1e-8,
            rel_tol=0,
        )
        for e in evaluation:
            assert sum(len(g["tracks"]) for g in e["receivers"]) == e["tracks"]
            for g in e["receivers"]:
                assert math.isclose(
                    sum(t["held_log_score"] for t in g["tracks"]),
                    g["held_log_score"],
                    abs_tol=1e-8,
                    rel_tol=0,
                )
                for t in g["tracks"]:
                    assert abs(sum(t["weights"]) - 1) < 1e-10
        distance = error(refined["estimate"], authority)
        row["polished"][arm] = {
            "state": "returned",
            "qualified": refined["qualified"],
            "horizontal_error_m": distance,
            "below_1km": refined["qualified"] and distance < 1000,
            "estimate": refined["estimate"],
            "training_log_score": refined["training_log_score"],
            "held_log_score": refined["held_log_score"],
            "max_abs_gradient": maximum,
            "held_observations": sum(e["held_observations"] for e in evaluation),
            "tracks": sum(e["tracks"] for e in evaluation),
            "original_qualified": refined["original_qualified"],
            "position_displacement_m": refined["position_displacement_m"],
            "training_score_change": refined["training_log_score"] - original["training_log_score"],
        }
        if arm == "receiver_slope":
            row["polished"][arm]["receiver_slopes_native_hz_s"] = refined["x"][-2:]
        refined_results[arm] = refined
        polishing_checks += 1
    if len(refined_results) == 2:
        a, b = refined_results["control"], refined_results["receiver_slope"]
        deltas = [
            y["held_log_score"] - x["held_log_score"]
            for x, y in zip(a["evaluation"], b["evaluation"], strict=True)
        ]
        assert [e["held_observations"] for e in a["evaluation"]] == [
            e["held_observations"] for e in b["evaluation"]
        ]
        row["polished_paired"] = {
            "geographic_delta_m": row["polished"]["receiver_slope"]["horizontal_error_m"]
            - row["polished"]["control"]["horizontal_error_m"],
            "held_log_score_delta": sum(deltas),
            "positive_held_records": sum(d > 0 for d in deltas),
            "held_deltas_by_record": deltas,
            "equal_record_mean_delta_nats_per_observation": statistics.mean(
                d / e["held_observations"] for d, e in zip(deltas, a["evaluation"], strict=True)
            ),
            "both_qualified": row["polished"]["control"]["qualified"]
            and row["polished"]["receiver_slope"]["qualified"],
        }
    curve = HERE / "curvature" / dataset / "result.json"
    row["curvature"] = (
        json.loads(curve.read_text()) if curve.exists() else {"state": "missing_curvature_result"}
    )
    if row["curvature"]["state"] == "checked":
        expected_folder = (
            "polished" if row["polished"]["receiver_slope"]["qualified"] else "results"
        )
        assert row["curvature"]["point_source"] == str(
            (HERE / expected_folder / dataset / "receiver_slope/result.json").relative_to(ROOT)
        )
    rows.append(row)

bootstrap = []
for item in json.loads((HERE / "bootstrap-evaluation.json").read_text()):
    unit = item["unit_id"]
    path = HERE / "bootstrap" / unit / "response.json"
    if not path.exists():
        bootstrap.append(item)
        continue
    r = json.loads(path.read_text())
    distance = error(r["estimate"], authorities["DS8"])
    bootstrap.append(
        {
            "unit_id": unit,
            "horizontal_error_m": distance,
            "estimate": r["estimate"],
            "qualified": r["converged"] and not r["boundary_hit"],
            "held_log_score": item.get("held_log_score"),
        }
    )
old_panel = json.loads((ROOT / "reports/2026_09_28_ds89_baseline_panel/scores.json").read_text())
old_ds8 = [
    r for r in old_panel["rows"] if r["unit_id"].startswith("DS8-") and r["state"] == "scored"
]
new_single = next(r for r in bootstrap if r["unit_id"] == "DS8-008")
updated = {
    "returned_records": len(old_ds8) + 1,
    "qualified_records": sum(r["qualified"] for r in old_ds8) + int(new_single["qualified"]),
    "below_1km_qualified": sum(r["below_1km"] for r in old_ds8)
    + int(new_single["qualified"] and new_single["horizontal_error_m"] < 1000),
    "median_all_returned_error_m": statistics.median(
        [r["horizontal_error_m"] for r in old_ds8] + [new_single["horizontal_error_m"]]
    ),
    "scope": "Follow-up completion; original seven-returned panel ledger remains unchanged.",
}
output = {
    "rows": rows,
    "bootstrap": bootstrap,
    "ds8_completed_individual_panel": updated,
    "audit": {
        "bindings": len(bindings),
        "geographic_checks": geographic_checks,
        "start_checks": start_checks,
        "polishing_checks": polishing_checks,
    },
}
with (HERE / "scores.json").open("x") as f:
    json.dump(output, f, indent=2, allow_nan=False)


def plot_comparison(plot_rows, stem, title):
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), constrained_layout=True)
    for k, arm in enumerate(("control", "receiver_slope")):
        values = [r[arm].get("horizontal_error_m", float("nan")) / 1000 for r in plot_rows]
        bars = axes[0].bar(
            np.arange(3) + (k - 0.5) * 0.3,
            values,
            width=0.28,
            color=("#52758f", "#d19a35")[k],
            label=("Original pooled model", "Two shared receiver slopes")[k],
        )
        for bar, r in zip(bars, plot_rows, strict=True):
            if not r[arm]["qualified"]:
                bar.set_hatch("///")
    axes[0].axhline(1, color="black", linestyle=":", linewidth=1)
    axes[0].set_ylabel("Horizontal error (km); hatched = unqualified")
    axes[0].legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), fontsize=8)
    axes[1].bar(
        np.arange(3),
        [
            r.get("paired", {}).get("held_log_score_delta", float("nan"))
            / r["control"].get("held_observations", 1)
            for r in plot_rows
        ],
        color="#d19a35",
    )
    axes[1].axhline(0, color="black", linewidth=0.8)
    axes[1].set_ylabel("Augmented − control held score (nats / observation)")
    for ax in axes:
        ax.set_xticks(np.arange(3), [r["dataset_id"] + " first eight" for r in plot_rows])
    fig.suptitle(title)
    fig.savefig(HERE / (stem + ".png"), dpi=170)
    fig.savefig(HERE / (stem + ".svg"))


plot_comparison(rows, "pooled", "Initial receiver-slope fits: separate eight-record budgets")
plot_comparison(
    [
        {"dataset_id": r["dataset_id"], **r["polished"], "paired": r.get("polished_paired", {})}
        for r in rows
    ],
    "pooled-polished",
    "Numerically refined receiver-slope fits: separate eight-record budgets",
)
print(json.dumps(output, indent=2))
