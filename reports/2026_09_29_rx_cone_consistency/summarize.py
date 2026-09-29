"""Aggregate fixed-axis cone support without excluding inconsistent tracks."""

import hashlib
import json
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
plan = json.loads((HERE / "plan.json").read_text())
bindings = {}
for f in [HERE / "input-seal.json", *HERE.glob("runs/*/seal.json")]:
    for name, digest in json.loads(f.read_text())["sha256"].items():
        assert name not in bindings or bindings[name] == digest
        bindings[name] = digest
for name, digest in bindings.items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name


def aggregate(rows, control, widths):
    selected = []
    scans = {}
    for row in rows:
        values = row["controls"][control]["widths"]
        value = next(r for r in values if r["half_angle_deg"] == widths[row["receiver"]])
        selected.append(value)
        scans.setdefault(row["session_id"], []).append(value)
    positive = [r for r in selected if r["training_posterior_mass"] > 0]
    return {
        "control": control,
        "rx0_half_angle_deg": widths[0],
        "rx1_half_angle_deg": widths[1],
        "tracks": len(rows),
        "unsupported_tracks": sum(r["supported_candidates"] == 0 for r in selected),
        "zero_stored_posterior_mass_tracks": len(selected) - len(positive),
        "mean_retained_training_mass": float(
            np.mean([r["training_posterior_mass"] for r in selected])
        ),
        "conditional_held_all_inside_mean": float(
            np.mean([r["conditional_held_all_inside_mass"] for r in positive])
        )
        if positive
        else None,
        "conditional_held_tracks": len(positive),
        "scans": len(scans),
        "fully_supported_scans": sum(
            all(r["supported_candidates"] > 0 for r in values) for values in scans.values()
        ),
        "recordings": [
            {
                "session_id": key,
                "tracks": len(values),
                "unsupported_tracks": sum(r["supported_candidates"] == 0 for r in values),
            }
            for key, values in scans.items()
        ],
    }


panel_results, all_rows, jobs = [], {}, []
for unit in plan["units"]:
    key, group = unit["unit_id"], unit["group"]
    parent = HERE / "runs" / key
    code = int((parent / "exit-code.txt").read_text())
    if code != 0:
        panel_results.append({"unit": key, "validated": False, "exit_code": code})
        continue
    result = json.loads((parent / "result.json").read_text())
    assert result["position_and_timings"] == unit["x"]
    rows = result["rows"]
    prior = json.loads((ROOT / unit["baseline_audit"]).read_text())
    original = {(r["session_id"], r["track_id"]): r for r in prior["rows"]}
    assert len(rows) == len(original) == group["tracks"]
    assert {(r["session_id"], r["track_id"]) for r in rows} == original.keys()
    assert sum(r["training_observations"] for r in rows) == group["training_observations"]
    assert sum(r["held_observations"] for r in rows) == group["held_observations"]
    for row in rows:
        source = original[row["session_id"], row["track_id"]]
        assert row["held_observations"] == source["held_observations"]
        assert row["candidates"] == len(source["weights"])
        for control in plan["controls"]:
            data = row["controls"][control]
            assert [r["half_angle_deg"] for r in data["widths"]] == plan["half_angles_deg"]
            counts, masses = [], []
            for r in data["widths"]:
                assert 0 <= r["supported_candidates"] <= row["candidates"]
                assert (r["supported_candidates"] > 0) == (
                    data["minimum_training_half_angle_deg"] <= r["half_angle_deg"]
                )
                assert 0 <= r["training_posterior_mass"] <= 1 + 1e-8
                if r["training_posterior_mass"] > 0:
                    assert 0 <= r["conditional_held_all_inside_mass"] <= 1 + 1e-8
                else:
                    assert r["conditional_held_all_inside_mass"] is None
                counts.append(r["supported_candidates"])
                masses.append(r["training_posterior_mass"])
            assert np.all(np.diff(counts) >= 0) and np.all(np.diff(masses) >= -1e-12)
    all_rows[key] = rows
    combinations = [
        aggregate(rows, c, (w0, w1))
        for c in plan["controls"]
        for w0 in plan["half_angles_deg"]
        for w1 in plan["half_angles_deg"]
    ]
    panel_results.append(
        {
            "unit": key,
            "dataset": group["source_dataset"],
            "size": group["size"],
            "block": group["block"],
            "validated": True,
            "combinations": combinations,
        }
    )

datasets = []
for ds in ("DS7", "DS8", "DS9"):
    groups = [
        u for u in plan["units"] if u["group"]["source_dataset"] == ds and u["group"]["size"] == 8
    ]
    complete = all(u["unit_id"] in all_rows for u in groups)
    if not complete:
        datasets.append({"dataset": ds, "validated": False})
        continue
    rows = [r for u in groups for r in all_rows[u["unit_id"]]]
    assert len({(r["session_id"], r["track_id"]) for r in rows}) == len(rows)
    assert len({r["session_id"] for r in rows}) == 24
    datasets.append(
        {
            "dataset": ds,
            "validated": True,
            "combinations": [
                aggregate(rows, c, (w0, w1))
                for c in plan["controls"]
                for w0 in plan["half_angles_deg"]
                for w1 in plan["half_angles_deg"]
            ],
        }
    )

for f in HERE.glob("runs/*/resources.txt"):
    content = f.read_text()
    wall = re.search(r"Elapsed \(wall clock\) time.*: ([\d:.]+)", content).group(1)
    seconds = 0.0
    for value in wall.split(":"):
        seconds = seconds * 60 + float(value)
    jobs.append(
        {
            "unit": f.parent.name,
            "wall_s": seconds,
            "max_rss_kib": int(
                re.search(r"Maximum resident set size \(kbytes\): (\d+)", content).group(1)
            ),
            "exit_code": int((f.parent / "exit-code.txt").read_text()),
        }
    )
summary = {
    "panels": panel_results,
    "datasets_eight_only": datasets,
    "execution_bindings_verified": len(bindings),
}
(HERE / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
(HERE / "resources.json").write_text(
    json.dumps(
        {
            "jobs": jobs,
            "total_job_wall_s": sum(r["wall_s"] for r in jobs),
            "max_job_wall_s": max(r["wall_s"] for r in jobs),
            "max_rss_kib": max(r["max_rss_kib"] for r in jobs),
        },
        indent=2,
    )
    + "\n"
)
fig, axes = plt.subplots(1, 3, figsize=(13, 4.2))
for ax, data in zip(axes, datasets, strict=True):
    ax.set_title(data["dataset"])
    if not data["validated"]:
        ax.text(0.5, 0.5, "Incomplete", ha="center")
        continue
    matrix = np.array(
        [
            100 * r["unsupported_tracks"] / r["tracks"]
            for r in data["combinations"]
            if r["control"] == "nominal"
        ]
    ).reshape(4, 4)
    ax.imshow(matrix, vmin=0, vmax=100, cmap="magma_r")
    ax.set_xticks(range(4), plan["half_angles_deg"])
    ax.set_yticks(range(4), plan["half_angles_deg"])
    ax.set_xlabel("RX1 cone half-angle (degrees)")
    ax.set_ylabel("RX0 cone half-angle (degrees)")
    for i in range(4):
        for j in range(4):
            ax.text(
                j,
                i,
                f"{matrix[i, j]:.1f}%",
                ha="center",
                va="center",
                color="white" if matrix[i, j] > 50 else "black",
            )
fig.suptitle(
    "Tracks with no whole-training-arc candidate inside the nominal cone\n"
    "24 distinct scans per dataset; frozen Doppler-selected positions"
)
fig.tight_layout()
for suffix in ("png", "svg"):
    fig.savefig(HERE / ("cone-support." + suffix), dpi=160)
print("Validated panels:", sum(r["validated"] for r in panel_results), "/", len(plan["units"]))
for data in datasets:
    if data["validated"]:
        print(
            data["dataset"],
            [
                (
                    r["rx0_half_angle_deg"],
                    r["unsupported_tracks"],
                    r["tracks"],
                    r["fully_supported_scans"],
                    r["mean_retained_training_mass"],
                )
                for r in data["combinations"]
                if r["control"] == "nominal" and r["rx0_half_angle_deg"] == r["rx1_half_angle_deg"]
            ],
        )
