"""Verify pooled timing panels against one-timing and free receiver baselines."""

import hashlib
import json
import math
import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
FREE = HERE.parent / "2026_09_29_split_receiver_timing"
sys.path.insert(0, str(ROOT / "tools"))
from ds7_eval import horizontal_error_m  # noqa: E402

plan = json.loads((HERE / "plan.json").read_text())
bindings = {}
for f in [HERE / "input-seal.json", *HERE.glob("runs/**/seal.json")]:
    for name, digest in json.loads(f.read_text())["sha256"].items():
        assert name not in bindings or bindings[name] == digest
        bindings[name] = digest
for name, digest in bindings.items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
references = set()
for members in plan["membership"].values():
    for member in members:
        path = ROOT / member["pose_path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == member["pose_sha256"]
        authority = json.loads(path.read_text())["pose_authority"]
        references.add((authority["latitude_deg"], authority["longitude_deg"]))
assert len(references) == 1
reference = next(iter(references))


def distance(estimate):
    lat, lon = estimate["latitude_deg"], estimate["longitude_deg"]
    value = horizontal_error_m(lat, lon, *reference)

    def vector(a, b):
        a, b = math.radians(a), math.radians(b)
        return np.array([math.cos(a) * math.cos(b), math.cos(a) * math.sin(b), math.sin(a)])

    a, b = vector(lat, lon), vector(*reference)
    independent = 6371008.8 * math.atan2(float(np.linalg.norm(np.cross(a, b))), float(a @ b))
    assert abs(value - independent) < 1e-4
    return value


rows, held, nested_validations, jobs = [], {}, [], []
for unit in plan["units"]:
    key, group = unit["unit_id"], unit["group"]
    parent = HERE / "runs" / key
    selection = json.loads((parent / "selection.json").read_text())
    eligible, generic, alternatives = [], [], []
    for start, run in zip(unit["starts"], selection["runs"], strict=True):
        folder = parent / "fit" / start["label"]
        code = int((folder / "exit-code.txt").read_text())
        assert code == run["exit_code"]
        result = run["result"]
        if result is None:
            assert code != 0
            alternatives.append({"start": start["label"], "exit_code": code})
            continue
        assert result == json.loads((folder / "result.json").read_text())
        assert result["initial"] == start["x"]
        assert result["session_ids"] == group["session_ids"] * 2
        x = np.asarray(result["x"])
        assert len(x) == 3 + group["size"]
        boundary = any(
            abs(v) > bound - 1e-3
            for v, bound in zip(x, [12] * 2 + [4] * group["size"] + [2], strict=True)
        )
        assert boundary == result["boundary_hit"]
        qualified = (
            result["success"] and not boundary and max(abs(np.array(result["gradient"]))) <= 0.01
        )
        assert bool(qualified) == result["qualified"]
        alternatives.append(
            {
                "start": start["label"],
                "exit_code": code,
                "qualified": bool(qualified),
                "error_m": distance(result["estimate"]),
                "training_log_score": result["training_log_score"],
                "message": result["message"],
            }
        )
        if qualified:
            eligible.append(result)
            if start["label"] != "nested":
                generic.append(result)
        if start["label"] == "nested":
            v = result["nested_validation"]
            assert v["held_rows_identical"] and v["tracks"] == group["tracks"]
            assert v["score_difference"] < 1e-7 and v["gradient_difference"] < 1e-7
            nested_validations.append({"unit": key, **v})
    selected = max(eligible, key=lambda r: r["training_log_score"]) if eligible else None
    assert selected == selection["selected"] and len(eligible) == selection["qualified_starts"]
    prior = json.loads((ROOT / unit["baseline_selection"]).read_text())["selected"]
    prior_held = json.loads((ROOT / unit["baseline_audit"]).read_text())
    free = json.loads((FREE / "runs" / key / "selection.json").read_text())["selected"]
    free_held = json.loads((FREE / "runs" / key / "held/result.json").read_text())
    assert free["qualified"] and free_held["audit_passed"]
    row = {
        "unit": key,
        "dataset": group["source_dataset"],
        "block": group["block"],
        "size": group["size"],
        "baseline_error_m": distance(prior["estimate"]),
        "free_timing_error_m": distance(free["estimate"]),
        "alternatives": alternatives,
        "validated": False,
        "qualified_starts": len(eligible),
    }
    if selected:
        code = int((parent / "held/exit-code.txt").read_text())
        row["audit_exit_code"] = code
        if code == 0:
            audit = json.loads((parent / "held/result.json").read_text())
            assert audit["x"] == selected["x"]
            assert abs(audit["training_log_score"] - selected["training_log_score"]) < 1e-7
            assert len(audit["gradient_checks"]) == len(selected["x"])
            for check in audit["gradient_checks"]:
                axis, steps = check["axis"], check["steps"]
                assert [s["step"] for s in steps] == (
                    [0.001, 0.0005] if axis < 2 else [0.0000625, 0.00003125]
                )
                passed = all(
                    s["absolute_difference"] < 0.002 and not s["crosses_grid_node"] for s in steps
                )
                passed &= axis < 2 or abs(steps[0]["numerical"] - steps[1]["numerical"]) < 0.002
                assert passed == check["passed"]
            assert audit["audit_passed"] == all(c["passed"] for c in audit["gradient_checks"])

            def by_key(values):
                return {(r["session_id"], r["track_id"]): r for r in values}

            old, new = by_key(prior_held["rows"]), by_key(audit["rows"])
            free_rows = by_key(free_held["rows"])
            assert free_rows.keys() == new.keys()
            assert all(
                free_rows[k]["held_observations"] == new[k]["held_observations"] for k in new
            )
            assert old.keys() == new.keys() and len(new) == len(audit["rows"]) == group["tracks"]
            assert all(old[k]["held_observations"] == new[k]["held_observations"] for k in old)
            assert sum(r["held_observations"] for r in new.values()) == group["held_observations"]
            assert (
                abs(
                    sum(r["training_log_score"] for r in new.values()) - audit["training_log_score"]
                )
                < 1e-7
            )
            assert (
                abs(sum(r["held_log_score"] for r in new.values()) - audit["held_log_score"]) < 1e-7
            )
            row.update(
                validated=audit["audit_passed"],
                error_m=distance(selected["estimate"]),
                selected_start=selected["start"],
                training_gain=selected["training_log_score"] - prior["training_log_score"],
                held_gain=audit["held_log_score"] - prior_held["held_log_score"],
                held_gain_vs_free=audit["held_log_score"] - free_held["held_log_score"],
                training_gain_vs_free=selected["training_log_score"] - free["training_log_score"],
                max_gradient_discrepancy=max(
                    s["absolute_difference"] for c in audit["gradient_checks"] for s in c["steps"]
                ),
                common_rx1_minus_rx0_s=selected["x"][-1],
            )
            if generic:
                g = max(generic, key=lambda r: r["training_log_score"])
                row["generic_selected"] = {
                    "start": g["start"],
                    "error_m": distance(g["estimate"]),
                    "training_gap_to_selected": g["training_log_score"]
                    - selected["training_log_score"],
                }
            held[key] = new
    rows.append(row)

aggregates, paired = [], []
for ds in ("DS7", "DS8", "DS9"):
    for size in (4, 8):
        subset = [r for r in rows if r["dataset"] == ds and r["size"] == size]
        valid = [r for r in subset if r["validated"]]
        aggregates.append(
            {
                "dataset": ds,
                "size": size,
                "planned": len(subset),
                "validated": len(valid),
                "median_error_m": float(np.median([r["error_m"] for r in valid]))
                if len(valid) == len(subset)
                else None,
                "validated_subset_median_error_m": float(np.median([r["error_m"] for r in valid]))
                if valid
                else None,
                "matched_baseline_median_error_m": float(
                    np.median([r["baseline_error_m"] for r in valid])
                )
                if valid
                else None,
                "matched_free_median_error_m": float(
                    np.median([r["free_timing_error_m"] for r in valid])
                )
                if valid
                else None,
                "subkm": sum(r["error_m"] < 1000 for r in valid),
                "held_improved": sum(r["held_gain"] > 0 for r in valid),
            }
        )
    for block in ("early", "middle", "late"):
        four, eight = f"{ds}_{block}_4", f"{ds}_{block}_8"
        if all(next(r for r in rows if r["unit"] == k)["validated"] for k in (four, eight)):
            a, b = held[four], held[eight]
            assert a.keys() <= b.keys()
            paired.append(
                {
                    "dataset": ds,
                    "block": block,
                    "held_observations": sum(r["held_observations"] for r in a.values()),
                    "eight_minus_four_held": sum(
                        b[k]["held_log_score"] - r["held_log_score"] for k, r in a.items()
                    ),
                }
            )

for f in HERE.glob("runs/**/resources.txt"):
    text = f.read_text()
    wall = re.search(r"Elapsed \(wall clock\) time.*: ([\d:.]+)", text).group(1)
    seconds = 0.0
    for v in wall.split(":"):
        seconds = seconds * 60 + float(v)
    jobs.append(
        {
            "job": str(f.parent.relative_to(HERE)),
            "wall_s": seconds,
            "max_rss_kib": int(
                re.search(r"Maximum resident set size \(kbytes\): (\d+)", text).group(1)
            ),
            "exit_code": int((f.parent / "exit-code.txt").read_text()),
        }
    )
resources = {
    "jobs": jobs,
    "total_job_wall_s": sum(j["wall_s"] for j in jobs),
    "max_job_wall_s": max(j["wall_s"] for j in jobs),
    "max_rss_kib": max(j["max_rss_kib"] for j in jobs),
}
summary = {
    "rows": rows,
    "aggregates": aggregates,
    "paired_held": paired,
    "nested_validations": nested_validations,
    "reference": reference,
    "execution_bindings_verified": len(bindings),
}
(HERE / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
(HERE / "resources.json").write_text(json.dumps(resources, indent=2) + "\n")
fig, axes = plt.subplots(1, 3, figsize=(15, 4.5), sharey=True)
for ax, ds in zip(axes, ("DS7", "DS8", "DS9"), strict=True):
    subset = [r for r in rows if r["dataset"] == ds]
    x = np.arange(len(subset))
    ax.plot(x, [r["baseline_error_m"] for r in subset], "o-", label="One timing / scan")
    ax.plot(x, [r["free_timing_error_m"] for r in subset], "^-", label="Independent RX differences")
    ax.plot(
        x,
        [r.get("error_m", np.nan) if r["validated"] else np.nan for r in subset],
        "s-",
        label="One common RX difference",
    )
    failed = [(i, r) for i, r in enumerate(subset) if not r["validated"] and "error_m" in r]
    if failed:
        ax.scatter(
            [i for i, r in failed],
            [r["error_m"] for i, r in failed],
            marker="x",
            color="red",
            s=70,
            label="Audit failed",
        )
        for i, r in failed:
            ax.annotate(
                "Audit failed",
                (i, r["error_m"]),
                xytext=(-65, 15),
                textcoords="offset points",
                color="red",
                fontsize=8,
            )
    ax.axhline(1000, color="grey", linestyle="--", label="1 km")
    ax.set_xticks(x, [r["block"] + "\n" + str(r["size"]) + " scans" for r in subset], fontsize=8)
    ax.set_title(ds)
axes[0].set_ylabel("Joint position error (m)")
axes[0].legend()
fig.suptitle("Fixed consecutive panels · shared position · unsurveyed reference")
fig.tight_layout()
for suffix in ("png", "svg"):
    fig.savefig(HERE / ("comparison." + suffix), dpi=160)
print(
    json.dumps(
        {
            "aggregates": aggregates,
            "validated": sum(r["validated"] for r in rows),
            "nested_validations": len(nested_validations),
            "bindings": len(bindings),
        },
        indent=2,
    )
)
