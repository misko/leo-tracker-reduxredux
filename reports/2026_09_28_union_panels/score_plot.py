"""Reconcile all source and target panels before geographic comparison."""

import hashlib
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
from ds7_eval import horizontal_error_m  # noqa: E402
from ds789_pool_plan import layout  # noqa: E402

plan = json.loads((HERE / "plan.json").read_text())
broad_separate = json.loads(
    (HERE.parent / "2026_09_28_temporal_coverage_models/scores.json").read_text()
)
broad_transfer = json.loads(
    (HERE.parent / "2026_09_28_temporal_coverage_transfer/scores.json").read_text()
)
for spec in plan["models"]:
    for unit in spec["units"]:
        if len(unit["source_datasets"]) >= 2:
            expected_layout = layout(spec["groups"], unit["excluded_dataset"])
            for key, value in expected_layout.items():
                assert unit[key] == value
        else:
            group = next(g for g in spec["groups"] if g["dataset_id"] == unit["source_datasets"][0])
            assert unit["session_ids"] == group["session_ids"]
            expected = [
                {"source_dataset": label, "x": position + group["point"][2:]}
                for label, position in (
                    ("broad", group["point"][:2]),
                    ("historical", group["historical_position"]),
                    ("origin", [0, 0]),
                )
            ]
            assert unit["starts"] == expected
bindings = {}
for path in [HERE / "input-seal.json", *HERE.glob("t*/**/seal.json")]:
    for name, sha in json.loads(path.read_text())["sha256"].items():
        assert name not in bindings or bindings[name] == sha
        bindings[name] = sha
for name, sha in bindings.items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == sha
reference_bindings = {}
for ds, records in plan["membership"].items():
    group = next(g for g in plan["models"][0]["groups"] if g["dataset_id"] == ds)
    name = group["manifest_path"]
    reference_bindings[name] = bindings[name]
    for record in records:
        reference_bindings[record["pose_path"]] = record["pose_sha256"]
references = set()
for name, sha in reference_bindings.items():
    path = ROOT / name
    assert hashlib.sha256(path.read_bytes()).hexdigest() == sha
    if "/pose/" in name:
        pose = json.loads(path.read_text())["pose_authority"]
        references.add((pose["latitude_deg"], pose["longitude_deg"]))
assert len(references) == 1
reference = next(iter(references))


def distance(estimate, coordinate=reference):
    value = horizontal_error_m(estimate["latitude_deg"], estimate["longitude_deg"], *coordinate)

    def vector(lat, lon):
        lat, lon = math.radians(lat), math.radians(lon)
        return np.array(
            [math.cos(lat) * math.cos(lon), math.cos(lat) * math.sin(lon), math.sin(lat)]
        )

    a, b = vector(estimate["latitude_deg"], estimate["longitude_deg"]), vector(*coordinate)
    other = 6371008.8 * math.atan2(float(np.linalg.norm(np.cross(a, b))), float(a @ b))
    assert abs(value - other) < 1e-4
    return value


def selected(parent, stage):
    selection = json.loads((parent / f"{stage}-selection.json").read_text())
    eligible = []
    for run in selection["runs"]:
        path = parent / f"{stage}_fit" / run["start_id"]
        assert int((path / "exit-code.txt").read_text()) == run["exit_code"]
        fit = run["result"]
        if fit is not None:
            assert fit == json.loads((path / "result.json").read_text())
            values = fit["x"][2:] if stage == "target" else fit["x"]
            limits = [5] * len(values) if stage == "target" else [12, 12] + [5] * (len(values) - 2)
            boundary = any(abs(v) > b - 0.001 for v, b in zip(values, limits, strict=True))
            assert fit["qualified"] == bool(
                fit["success"] and not boundary and max(abs(g) for g in fit["gradient"]) <= 0.01
            )
            if fit["qualified"]:
                eligible.append(fit)
    expected = max(eligible, key=lambda r: r["training_log_score"]) if eligible else None
    assert selection["selected"] == expected
    return selection, eligible


def comparison(parent, stage, chosen, groups, decay):
    folder = parent / f"{stage}_held"
    if not folder.exists():
        return {"state": "not_run"}
    code = int((folder / "exit-code.txt").read_text())
    if code:
        return {"state": "failed", "exit_code": code}
    result = json.loads((folder / "result.json").read_text())
    assert abs(result["training_log_score"] - chosen["training_log_score"]) < 1e-7
    assert (
        abs(sum(r["training_log_score"] for r in result["rows"]) - result["training_log_score"])
        < 1e-7
    )
    assert abs(sum(r["held_log_score"] for r in result["rows"]) - result["held_log_score"]) < 1e-7
    details = []
    for group in groups:
        ds = group["dataset_id"]
        baseline_folder = HERE / f"t{decay}" / ("single_" + ds) / "source_held"
        if not (baseline_folder / "result.json").exists():
            return {"state": "separate_panel_missing", "dataset": ds}
        assert int((baseline_folder / "exit-code.txt").read_text()) == 0
        covariance = json.loads((baseline_folder / "result.json").read_text())
        old_cov = {(r["session_id"], r["track_id"]): r for r in covariance["rows"]}
        rows = [r for r in result["rows"] if r["session_id"] in group["session_ids"]]
        assert {(r["session_id"], r["track_id"]) for r in rows} == set(old_cov)
        assert len(old_cov) == len(rows)
        assert all(
            r["held_observations"] == old_cov[(r["session_id"], r["track_id"])]["held_observations"]
            for r in rows
        )
        record_deltas = []
        for session in group["session_ids"]:
            current = [r for r in rows if r["session_id"] == session]
            record_deltas.append(
                {
                    "session_id": session,
                    "training_vs_same_model_panel": sum(
                        r["training_log_score"]
                        - old_cov[(session, r["track_id"])]["training_log_score"]
                        for r in current
                    ),
                    "vs_same_model_panel": sum(
                        r["held_log_score"] - old_cov[(session, r["track_id"])]["held_log_score"]
                        for r in current
                    ),
                }
            )
        details.append(
            {
                "dataset": ds,
                "tracks": len(rows),
                "held_observations": sum(r["held_observations"] for r in rows),
                "held_delta_vs_same_model_panel": sum(
                    r["vs_same_model_panel"] for r in record_deltas
                ),
                "training_delta_vs_same_model_panel": sum(
                    r["training_vs_same_model_panel"] for r in record_deltas
                ),
                "positive_records_vs_same_model": sum(
                    r["vs_same_model_panel"] > 0 for r in record_deltas
                ),
                "record_deltas": record_deltas,
            }
        )
    return {
        "state": "returned",
        "datasets": details,
        "gradient_check": result["position_gradient_check"],
        "offset_stationarity": result["offset_stationarity"],
    }


rows = []
for spec in plan["models"]:
    decay = spec["decay_s"]
    for unit in spec["units"]:
        parent = HERE / f"t{decay}" / unit["unit_id"]
        selection, eligible = selected(parent, "source")
        chosen = selection["selected"]
        row = {
            "decay_s": decay,
            "unit_id": unit["unit_id"],
            "source_datasets": unit["source_datasets"],
            "excluded_dataset": unit["excluded_dataset"],
            "planned_starts": len(unit["starts"]),
            "qualified_starts": len(eligible),
            "selected": chosen,
        }
        row["source_runs"] = selection["runs"]
        row["source_start_errors_m"] = {
            run["start_id"]: distance(run["result"]["estimate"])
            for run in selection["runs"]
            if run["result"] is not None
        }
        row["higher_score_unqualified_starts"] = [
            {
                "start_id": r["start_id"],
                "training_score_advantage": r["result"]["training_log_score"]
                - chosen["training_log_score"],
                "max_abs_gradient": max(abs(g) for g in r["result"]["gradient"]),
            }
            for r in selection["runs"]
            if chosen is not None
            and r["result"] is not None
            and not r["result"]["qualified"]
            and r["result"]["training_log_score"] > chosen["training_log_score"]
        ]
        if chosen is not None:
            row["error_m"] = distance(chosen["estimate"])
            row["start_separation_m"] = max(
                distance(
                    a["estimate"], (b["estimate"]["latitude_deg"], b["estimate"]["longitude_deg"])
                )
                for a in eligible
                for b in eligible
            )
            source_groups = [
                g for g in spec["groups"] if g["dataset_id"] in unit["source_datasets"]
            ]
            assert chosen["session_ids"] == unit["session_ids"]
            row["source_held"] = comparison(parent, "source", chosen, source_groups, decay)
            if unit["excluded_dataset"] is not None:
                target_selection, targets = selected(parent, "target")
                target = target_selection["selected"]
                row["target_qualified_starts"] = len(targets)
                row["target_selected"] = target
                if target is not None:
                    assert target["x"][:2] == chosen["x"][:2]
                    target_groups = [
                        g for g in spec["groups"] if g["dataset_id"] == unit["excluded_dataset"]
                    ]
                    assert target["session_ids"] == target_groups[0]["session_ids"]
                    row["target_held"] = comparison(parent, "target", target, target_groups, decay)
        if unit["unit_id"].startswith("single_"):
            family = "shared" if decay == 0 else "correlated"
            row["broad_panel_error_m"] = next(
                r["error_m"]
                for r in broad_separate["rows"]
                if r["dataset"] == unit["source_datasets"][0] and r["family"] == family
            )
        else:
            previous_unit = "all24" if unit["unit_id"] == "all45" else unit["unit_id"]
            row["broad_panel_error_m"] = next(
                r["error_m"]
                for r in broad_transfer["rows"]
                if r["unit_id"] == previous_unit and r["decay_s"] == decay
            )
        rows.append(row)
panels = []
for group in plan["models"][0]["groups"]:
    ds = group["dataset_id"]
    held_path = HERE / "t0" / ("single_" + ds) / "source_held/result.json"
    if not held_path.exists():
        continue
    held = json.loads(held_path.read_text())
    eligible = {(r["session_id"], r["track_id"]): r for r in held["rows"]}
    other_path = HERE / "t10" / ("single_" + ds) / "source_held/result.json"
    if other_path.exists():
        other = json.loads(other_path.read_text())
        assert {(r["session_id"], r["track_id"]) for r in other["rows"]} == set(eligible)
        assert all(
            r["held_observations"]
            == eligible[(r["session_id"], r["track_id"])]["held_observations"]
            for r in other["rows"]
        )
    train_count = held_count = 0
    for item in group["inputs"]:
        artifact = next(a for a in item["artifacts"] if a["kind"] == "observations")
        observation = json.loads(Path(artifact["path"]).read_text())
        for track in observation["tracks"]:
            key = (item["session_id"], track["track_id"])
            if key in eligible:
                count = sum(track["training_mask"])
                train_count += count
                count_held = len(track["training_mask"]) - count
                assert count_held == eligible[key]["held_observations"]
                held_count += count_held
    records = plan["membership"][ds]
    panels.append(
        {
            "dataset": ds,
            "records": len(records),
            "tracks": len(eligible),
            "training_observations": train_count,
            "held_observations": held_count,
            "capture_start_span_h": (
                records[-1]["capture_start_utc_ns"] - records[0]["capture_start_utc_ns"]
            )
            / 3.6e12,
            "sample_rate_counts": dict(Counter(r["sample_rate_hz"] for r in records)),
        }
    )
scores = {
    "rows": rows,
    "reference": reference,
    "execution_bindings_verified": len(bindings),
    "reference_bindings": reference_bindings,
    "panels": panels,
}
(HERE / "scores.json").write_text(json.dumps(scores, indent=2, allow_nan=False) + "\n")
resources = []
for path in sorted(HERE.glob("t*/**/resources.txt")):
    content = path.read_text()
    elapsed = re.search(r"Elapsed \(wall clock\) time.*: (\S+)", content).group(1)
    seconds = 0.0
    for part in elapsed.split(":"):
        seconds = seconds * 60 + float(part)
    rss = int(re.search(r"Maximum resident set size \(kbytes\): (\d+)", content).group(1))
    resources.append(
        {
            "job": str(path.parent.relative_to(HERE)),
            "wall_s": seconds,
            "max_rss_kib": rss,
            "exit_code": int((path.parent / "exit-code.txt").read_text()),
        }
    )
(HERE / "resource-summary.json").write_text(
    json.dumps(
        {
            "jobs": resources,
            "total_job_wall_s": sum(r["wall_s"] for r in resources),
            "max_job_wall_s": max(r["wall_s"] for r in resources),
            "max_rss_kib": max(r["max_rss_kib"] for r in resources),
        },
        indent=2,
    )
    + "\n"
)
fig, axes = plt.subplots(1, 2, figsize=(14, 5), layout="constrained")
units = ["all45", "exclude_DS7", "exclude_DS8", "exclude_DS9"]
xs = np.arange(4)
for dx, decay, label in ((-0.18, 0, "Shared scale"), (0.18, 10, "10-second correlation")):
    selected_rows = [
        next(r for r in rows if r["decay_s"] == decay and r["unit_id"] == u) for u in units
    ]
    color = "tab:orange" if decay == 0 else "tab:green"
    axes[0].bar(
        xs + dx,
        [r.get("error_m", np.nan) for r in selected_rows],
        width=0.36,
        label=label,
        color=color,
    )
    changes = [
        r.get("target_held", {})
        .get("datasets", [{}])[0]
        .get("held_delta_vs_same_model_panel", np.nan)
        for r in selected_rows[1:]
    ]
    axes[1].bar(np.arange(3) + dx, changes, width=0.36, label=label, color=color)
axes[0].set_xticks(xs, ["All 45", "Without DS7", "Without DS8", "Without DS9"])
axes[0].set_ylabel("Nominal error against unsurveyed reference (m)")
axes[0].axhline(1000, color="black", ls="--", lw=0.8)
axes[0].set_title("Pooled and donor-position geography")
axes[1].set_xticks(np.arange(3), ["DS7", "DS8", "DS9"])
axes[1].set_ylabel("Target held change vs same-model own-panel fit (nats)")
axes[1].axhline(0, color="black", lw=0.8)
axes[1].set_title("Transfer to the excluded dataset")
for ax in axes:
    ax.legend(fontsize=8)
fig.suptitle("Union panels: 15 recordings per dataset; target geography fixed to donor fit")
fig.savefig(HERE / "covariance-transfer.png", dpi=170)
fig.savefig(HERE / "covariance-transfer.svg")
fig2, axes2 = plt.subplots(1, 2, figsize=(11, 4), sharey=True, layout="constrained")
for ax, decay, label in zip(
    axes2, (0, 10), ("Shared track scale", "10-second correlation"), strict=True
):
    items = [
        next(r for r in rows if r["decay_s"] == decay and r["unit_id"] == "single_" + ds)
        for ds in ("DS7", "DS8", "DS9")
    ]
    xs2 = np.arange(3)
    ax.bar(xs2 - 0.18, [r["broad_panel_error_m"] for r in items], width=0.36, label="Broad eight")
    ax.bar(xs2 + 0.18, [r.get("error_m", np.nan) for r in items], width=0.36, label="Union fifteen")
    ax.set_xticks(xs2, ["DS7", "DS8", "DS9"])
    ax.axhline(1000, color="black", ls="--", lw=0.8)
    ax.set_title(label)
    ax.legend(fontsize=8)
axes2[0].set_ylabel("Nominal error against unsurveyed reference (m)")
fig2.suptitle("Separate dataset fits; union adds seven historical recordings")
fig2.savefig(HERE / "separate-panels.png", dpi=170)
fig2.savefig(HERE / "separate-panels.svg")
print(json.dumps(scores, indent=2))
