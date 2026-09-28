"""Sealed temporal-panel model comparison with independently bound poses."""

import hashlib
import json
import math
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
INPUT = HERE.parent / "2026_09_28_temporal_coverage_inputs"
sys.path.insert(0, str(ROOT / "tools"))
from ds7_eval import horizontal_error_m  # noqa: E402

plan = json.loads((INPUT / "plan.json").read_text())
old = json.loads((HERE.parent / "2026_09_28_covariance_position/scores.json").read_text())
bindings = {}
for seal in HERE.glob("DS*/*/*/seal.json"):
    for path, sha in json.loads(seal.read_text())["sha256"].items():
        assert path not in bindings or bindings[path] == sha
        bindings[path] = sha
for path, sha in bindings.items():
    assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == sha, path
references = {}
reference_bindings = {}
rows = []


def error(estimate, reference):
    value = horizontal_error_m(estimate["latitude_deg"], estimate["longitude_deg"], *reference)

    def v(lat, lon):
        lat, lon = math.radians(lat), math.radians(lon)
        return np.array(
            [math.cos(lat) * math.cos(lon), math.cos(lat) * math.sin(lon), math.sin(lat)]
        )

    a, b = v(estimate["latitude_deg"], estimate["longitude_deg"]), v(*reference)
    independent = 6371008.8 * math.atan2(float(np.linalg.norm(np.cross(a, b))), float(a @ b))
    assert abs(value - independent) < 1e-4
    return value


for dataset in ("DS7", "DS8", "DS9"):
    captures = [r for r in plan["captures"] if r["dataset_id"] == dataset]
    for capture in captures:
        manifest_path = ROOT / capture["dataset_manifest_path"]
        manifest = json.loads(manifest_path.read_text())
        assert (
            "sha256:" + hashlib.sha256(manifest_path.read_bytes()).hexdigest()
            == capture["dataset_sha256"]
        )
        reference_bindings[str(manifest_path.relative_to(ROOT))] = hashlib.sha256(
            manifest_path.read_bytes()
        ).hexdigest()
        row = next(c for c in manifest["captures"] if c["session_id"] == capture["session_id"])
        pose_path = manifest_path.parent / "pose" / (capture["session_id"] + ".json")
        sha = hashlib.sha256(pose_path.read_bytes()).hexdigest()
        assert "sha256:" + sha == row["pose_file_sha256"]
        pose = json.loads(pose_path.read_text())["pose_authority"]
        coordinate = (pose["latitude_deg"], pose["longitude_deg"])
        assert dataset not in references or references[dataset] == coordinate
        references[dataset] = coordinate
        reference_bindings[str(pose_path.relative_to(ROOT))] = sha
    for family in ("iid", "shared", "correlated"):
        parent = HERE / dataset / family
        selection = json.loads((parent / "selection.json").read_text())
        eligible = []
        for run in selection["runs"]:
            folder = parent / run["stage"]
            assert int((folder / "exit-code.txt").read_text()) == run["exit_code"]
            fit = run["result"]
            if fit is not None:
                assert fit == json.loads((folder / "result.json").read_text())
                boundary = any(
                    abs(v) > b - 0.001 for v, b in zip(fit["x"], [12, 12] + [5] * 8, strict=True)
                )
                assert fit["qualified"] == bool(
                    fit["success"] and not boundary and max(abs(g) for g in fit["gradient"]) <= 0.01
                )
                if fit["qualified"]:
                    eligible.append(fit)
        expected = max(eligible, key=lambda r: r["training_log_score"]) if eligible else None
        assert expected == selection["selected"]
        before = (
            old["original_errors_m"][dataset]
            if family == "iid"
            else next(
                r["error_m"]
                for r in old["rows"]
                if r["dataset"] == dataset and r["decay_s"] == (0 if family == "shared" else 10)
            )
        )
        row = {
            "dataset": dataset,
            "family": family,
            "historical_first_eight_error_m": before,
            "qualified_starts": len(eligible),
            "runs": selection["runs"],
            "selected": expected,
        }
        if expected is not None:
            row["error_m"] = error(expected["estimate"], references[dataset])
            row["start_separation_m"] = max(
                error(
                    a["estimate"], (b["estimate"]["latitude_deg"], b["estimate"]["longitude_deg"])
                )
                for a in eligible
                for b in eligible
            )
            row["higher_score_unqualified_starts"] = [
                r["stage"]
                for r in selection["runs"]
                if r["result"] is not None
                and not r["result"]["qualified"]
                and r["result"]["training_log_score"] > expected["training_log_score"]
            ]
            code = int((parent / "held/exit-code.txt").read_text())
            row["held_exit_code"] = code
            if code == 0:
                held = json.loads((parent / "held/result.json").read_text())
                assert abs(held["training_log_score"] - expected["training_log_score"]) < 1e-7
                assert (
                    abs(
                        sum(r["training_log_score"] for r in held["rows"])
                        - held["training_log_score"]
                    )
                    < 1e-7
                )
                assert (
                    abs(sum(r["held_log_score"] for r in held["rows"]) - held["held_log_score"])
                    < 1e-7
                )
                assert len({(r["session_id"], r["track_id"]) for r in held["rows"]}) == len(
                    held["rows"]
                )
                expected_observations = sum(
                    json.loads((INPUT / "validated" / (c["unit_id"] + ".json")).read_text())[
                        "held_observations"
                    ]
                    for c in captures
                )
                assert sum(r["held_observations"] for r in held["rows"]) == expected_observations
                row.update(
                    held_log_score=held["held_log_score"],
                    held_observations=expected_observations,
                    tracks=len(held["rows"]),
                    gradient_check=held["gradient_check"],
                )
        rows.append(row)
for row in rows:
    if row["family"] == "iid" or row.get("held_exit_code") != 0:
        continue
    iid = next(r for r in rows if r["dataset"] == row["dataset"] and r["family"] == "iid")
    if iid.get("held_exit_code") != 0:
        continue
    before = json.loads((HERE / row["dataset"] / "iid/held/result.json").read_text())["rows"]
    after = json.loads((HERE / row["dataset"] / row["family"] / "held/result.json").read_text())[
        "rows"
    ]
    indexed = {(r["session_id"], r["track_id"]): r for r in before}
    assert {(r["session_id"], r["track_id"]) for r in after} == set(indexed)
    paired = [
        {
            "session_id": session,
            "held_delta": sum(
                r["held_log_score"] - indexed[(session, r["track_id"])]["held_log_score"]
                for r in after
                if r["session_id"] == session
            ),
        }
        for session in sorted({r["session_id"] for r in after})
    ]
    row["paired_records_vs_iid"] = paired
    row["held_delta_vs_iid"] = sum(r["held_delta"] for r in paired)
scores = {
    "rows": rows,
    "references": references,
    "reference_bindings": reference_bindings,
    "execution_bindings_verified": len(bindings),
}
(HERE / "scores.json").write_text(json.dumps(scores, indent=2, allow_nan=False) + "\n")
fig, axes = plt.subplots(1, 3, figsize=(14, 4.5), layout="constrained", sharey=True)
for ax, ds in zip(axes, ("DS7", "DS8", "DS9"), strict=True):
    subset = [r for r in rows if r["dataset"] == ds]
    xs = np.arange(3)
    ax.bar(
        xs - 0.18,
        [r["historical_first_eight_error_m"] for r in subset],
        width=0.36,
        label="Historical first eight",
    )
    ax.bar(
        xs + 0.18,
        [r.get("error_m", np.nan) for r in subset],
        width=0.36,
        label="Broad temporal panel",
    )
    ax.axhline(1000, color="black", ls="--", lw=0.8)
    ax.set_xticks(xs, ["iid", "Shared scale", "Correlated"])
    ax.set_title(ds)
axes[0].set_ylabel("Nominal error against unsurveyed reference (m)")
axes[0].legend(fontsize=8)
fig.suptitle("Fixed models, eight records per panel · sample-rate mix and starts also differ")
fig.savefig(HERE / "temporal-models.png", dpi=170)
fig.savefig(HERE / "temporal-models.svg")
print(json.dumps(scores, indent=2))
