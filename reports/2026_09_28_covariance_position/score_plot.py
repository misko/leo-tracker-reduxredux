"""Post-fit geographic scoring and paired nuisance/position ablations."""

import hashlib
import json
import math
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from ds7_eval import horizontal_error_m  # noqa: E402

plan = json.loads((HERE.parent / "2026_09_28_cross_dataset_position/plan.json").read_text())
folders = {
    "DS7": "2026_09_27_ds7_post_ds6",
    "DS8": "2026_09_28_ds8_post_ds7",
    "DS9": "2026_09_28_ds9_post_ds8",
}
bindings = {}
for seal in HERE.glob("DS*/t*/*/seal.json"):
    for path, sha in json.loads(seal.read_text())["sha256"].items():
        assert path not in bindings or bindings[path] == sha
        bindings[path] = sha
for path, sha in bindings.items():
    assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == sha
references, reference_bindings, rows, original_errors = {}, {}, [], {}


def error(estimate, reference):
    value = horizontal_error_m(estimate["latitude_deg"], estimate["longitude_deg"], *reference)

    def unit(lat, lon):
        lat, lon = math.radians(lat), math.radians(lon)
        return np.array(
            [math.cos(lat) * math.cos(lon), math.cos(lat) * math.sin(lon), math.sin(lat)]
        )

    a, b = unit(estimate["latitude_deg"], estimate["longitude_deg"]), unit(*reference)
    independent = 6371008.8 * math.atan2(float(np.linalg.norm(np.cross(a, b))), float(a @ b))
    assert abs(value - independent) < 1e-4
    return value


for group in plan["groups"]:
    ds = group["dataset_id"]
    dataset_dir = HERE.parent / folders[ds]
    manifest_path = dataset_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    first = sorted(
        manifest["captures"], key=lambda c: (c["capture_start_utc_ns"], c["session_id"])
    )[:8]
    assert [c["session_id"] for c in first] == group["session_ids"]
    reference_bindings[str(manifest_path.relative_to(ROOT))] = hashlib.sha256(
        manifest_path.read_bytes()
    ).hexdigest()
    for capture in first:
        pose_path = dataset_dir / "pose" / (capture["session_id"] + ".json")
        sha = hashlib.sha256(pose_path.read_bytes()).hexdigest()
        assert "sha256:" + sha == capture["pose_file_sha256"]
        pose = json.loads(pose_path.read_text())["pose_authority"]
        coordinate = (pose["latitude_deg"], pose["longitude_deg"])
        assert ds not in references or references[ds] == coordinate
        references[ds] = coordinate
        reference_bindings[str(pose_path.relative_to(ROOT))] = sha
    original = json.loads((ROOT / group["source_point_path"]).read_text())
    original_errors[ds] = error(original["estimate"], references[ds])
    old_rows = {
        (r["session_id"], t["track_id"]): t
        for r in original["evaluation"]
        for rx in r["receivers"]
        for t in rx["tracks"]
    }
    original_held = sum(r["held_log_score"] for r in original["evaluation"])
    for decay in (0, 10):
        target = HERE / ds / f"t{decay}"
        selection = json.loads((target / "selection.json").read_text())
        starts = []
        for name in ("fit_original", "fit_origin"):
            path = target / name
            code = int((path / "exit-code.txt").read_text())
            returned = json.loads((path / "result.json").read_text()) if code == 0 else None
            if returned is not None:
                bound = any(
                    abs(v) > limit - 0.001
                    for v, limit in zip(returned["x"], [12, 12] + [5] * 8, strict=True)
                )
                assert returned["qualified"] == bool(
                    returned["success"]
                    and not bound
                    and max(abs(g) for g in returned["gradient"]) <= 0.01
                )
            starts.append({"start": name, "exit_code": code, "result": returned})
        qualified = [
            s["result"] for s in starts if s["result"] is not None and s["result"]["qualified"]
        ]
        expected = max(qualified, key=lambda f: f["training_log_score"]) if qualified else None
        assert expected == selection["selected"]
        row = {
            "dataset": ds,
            "decay_s": decay,
            "starts": starts,
            "qualified_starts": len(qualified),
            "original_error_m": original_errors[ds],
        }
        selected = selection["selected"]
        if selected is not None:
            row.update(error_m=error(selected["estimate"], references[ds]), selected=selected)
            row["qualified_start_separation_m"] = max(
                error(
                    a["estimate"], (b["estimate"]["latitude_deg"], b["estimate"]["longitude_deg"])
                )
                for a in qualified
                for b in qualified
            )
            diagnostic_path = target / "diagnostic"
            code = int((diagnostic_path / "exit-code.txt").read_text())
            row["diagnostic_exit_code"] = code
            if code == 0:
                diag = json.loads((diagnostic_path / "result.json").read_text())
                pre = json.loads((target / "preflight/result.json").read_text())
                assert {(r["session_id"], r["track_id"]) for r in diag["rows"]} == set(old_rows)
                assert (
                    abs(
                        sum(r["training_log_score"] for r in diag["rows"])
                        - selected["training_log_score"]
                    )
                    < 1e-7
                )
                assert (
                    abs(sum(r["held_log_score"] for r in diag["rows"]) - diag["held_log_score"])
                    < 1e-7
                )
                shadow = json.loads(
                    (
                        HERE.parent / f"2026_09_28_correlated_residual_shadow/{ds}/result.json"
                    ).read_text()
                )
                frozen = next(a for a in shadow["arms"] if a["id"] == f"mvt_s100_t{decay}")
                paired = [
                    {
                        "session_id": session,
                        "held_delta": sum(
                            r["held_log_score"]
                            - old_rows[(r["session_id"], r["track_id"])]["held_log_score"]
                            for r in diag["rows"]
                            if r["session_id"] == session
                        ),
                    }
                    for session in group["session_ids"]
                ]
                row.update(
                    held_delta_vs_original=diag["held_log_score"] - original_held,
                    frozen_covariance_held_gain=frozen["held"] - original_held,
                    offset_refit_held_increment=pre["initial_held_score"] - frozen["held"],
                    geographic_refit_held_increment=diag["held_log_score"]
                    - pre["initial_held_score"],
                    held_observations=sum(r["held_observations"] for r in diag["rows"]),
                    paired_records=paired,
                    gradient_check=diag["gradient_check"],
                    offset_stationarity=diag["offset_stationarity"],
                    hessian_asymmetry=diag["hessian_asymmetry"],
                    nuisance_eigenvalues=diag["nuisance_eigenvalues"],
                    profiled_position_eigenvalues=diag["profiled_position_eigenvalues"],
                )
                assert (
                    abs(sum(r["held_delta"] for r in paired) - row["held_delta_vs_original"]) < 1e-7
                )
        rows.append(row)
scores = {
    "rows": rows,
    "references": references,
    "original_errors_m": original_errors,
    "execution_bindings_verified": len(bindings),
    "reference_bindings": reference_bindings,
}
(HERE / "scores.json").write_text(json.dumps(scores, indent=2, allow_nan=False) + "\n")

fig, axes = plt.subplots(1, 2, figsize=(13, 5), layout="constrained")
xs = np.arange(3)
axes[0].bar(xs - 0.25, list(original_errors.values()), width=0.25, label="Original iid")
for dx, decay, label in (
    (0, 0, "Shared scale, zero correlation"),
    (0.25, 10, "10-second correlation"),
):
    selected = [r for r in rows if r["decay_s"] == decay]
    axes[0].bar(xs + dx, [r.get("error_m", np.nan) for r in selected], width=0.25, label=label)
    axes[1].bar(
        xs + (dx - 0.125),
        [r.get("held_delta_vs_original", np.nan) for r in selected],
        width=0.25,
        label=label,
    )
for ax in axes:
    ax.set_xticks(xs, ["DS7", "DS8", "DS9"])
    ax.legend(fontsize=8)
axes[0].axhline(1000, color="black", ls="--", lw=0.8)
axes[0].set_ylabel("Error against exposed unsurveyed reference (m)")
axes[0].set_title("Does the refit improve geography?")
axes[1].axhline(0, color="black", lw=0.8)
axes[1].set_ylabel("Held gain against original iid model (nats)")
axes[1].set_title("Predictive score evaluated separately")
fig.suptitle("First eight records per dataset · training-only nuisance and position fits")
fig.savefig(HERE / "covariance-position.png", dpi=170)
fig.savefig(HERE / "covariance-position.svg")
print(json.dumps(scores, indent=2))
