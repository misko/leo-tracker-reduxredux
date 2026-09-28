"""Post-seal geographic and paired held scoring with all units retained."""

import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
from ds7_eval import horizontal_error_m  # noqa: E402

plan = json.loads((HERE / "plan.json").read_text())
bindings = {}
for file in HERE.glob("*/**/seal.json"):
    for name, sha in json.loads(file.read_text())["sha256"].items():
        assert name not in bindings or bindings[name] == sha, name
        bindings[name] = sha
for name, sha in bindings.items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == sha, name

references, original, membership, reference_bindings = {}, {}, {}, {}
folders = {
    "DS7": "2026_09_27_ds7_post_ds6",
    "DS8": "2026_09_28_ds8_post_ds7",
    "DS9": "2026_09_28_ds9_post_ds8",
}
previous_plan = json.loads((HERE.parent / "2026_09_28_pooled_receiver_slope/plan.json").read_text())
for group in plan["groups"]:
    dataset = group["dataset_id"]
    folder = ROOT / "reports" / folders[dataset]
    manifest = json.loads((folder / "manifest.json").read_text())
    original_request_path = next(
        r["request_path"] for r in previous_plan if r["dataset_id"] == dataset
    )
    original_request = json.loads((ROOT / original_request_path).read_text())
    assert (
        original_request["dataset_sha256"]
        == "sha256:" + hashlib.sha256((folder / "manifest.json").read_bytes()).hexdigest()
    )
    reference_bindings[str((folder / "manifest.json").relative_to(ROOT))] = hashlib.sha256(
        (folder / "manifest.json").read_bytes()
    ).hexdigest()
    first = sorted(
        manifest["captures"], key=lambda r: (r["capture_start_utc_ns"], r["session_id"])
    )[:8]
    assert [c["session_id"] for c in first] == group["session_ids"]
    for capture in first:
        pose = folder / "pose" / (capture["session_id"] + ".json")
        sha = hashlib.sha256(pose.read_bytes()).hexdigest()
        assert "sha256:" + sha == capture["pose_file_sha256"]
        authority = json.loads(pose.read_text())["pose_authority"]
        coordinate = (authority["latitude_deg"], authority["longitude_deg"])
        assert dataset not in references or references[dataset] == coordinate
        references[dataset] = coordinate
        reference_bindings[str(pose.relative_to(ROOT))] = sha
        membership[capture["session_id"]] = dataset
    source = json.loads((ROOT / group["source_point_path"]).read_text())
    assert source["qualified"]
    original[dataset] = source
assert len(set(references.values())) == 1, (
    "shared-position assumption differs from bound site references"
)
reference = references["DS7"]
checks = 0


def error(estimate):
    global checks
    result = horizontal_error_m(estimate["latitude_deg"], estimate["longitude_deg"], *reference)

    def vector(lat, lon):
        lat, lon = math.radians(lat), math.radians(lon)
        return np.array(
            [math.cos(lat) * math.cos(lon), math.cos(lat) * math.sin(lon), math.sin(lat)]
        )

    a, b = vector(estimate["latitude_deg"], estimate["longitude_deg"]), vector(*reference)
    independent = 6371008.8 * math.atan2(float(np.linalg.norm(np.cross(a, b))), float(a @ b))
    assert abs(result - independent) < 1e-4
    checks += 1
    return result


def load_selection(folder, stage):
    selection = json.loads((folder / f"{stage}-selection.json").read_text())
    successful = [r for r in selection["runs"] if r is not None and r["success"]]
    expected = max(successful, key=lambda r: r["training_log_score"]) if successful else None
    assert selection["selected"] == expected
    for r in selection["runs"]:
        if r is None:
            continue
        values = r["x"][2:] if stage == "target" else r["x"]
        bounds = (
            [5.0] * len(values) if stage == "target" else [12.0, 12.0] + [5.0] * (len(values) - 2)
        )
        boundary = any(
            min(abs(v - b), abs(v + b)) < 1e-3 for v, b in zip(values, bounds, strict=True)
        )
        assert boundary == r["boundary_hit"]
        assert r["qualified"] == bool(
            r["success"] and not boundary and max(abs(v) for v in r["gradient"]) <= 0.01
        )
    return selection


def held_comparison(path, selected):
    if not path.exists():
        return {"state": "unavailable"}
    result = json.loads(path.read_text())
    rows = result["evaluation"]
    assert abs(sum(r["training_log_score"] for r in rows) - selected["training_log_score"]) < 1e-7
    assert abs(sum(r["held_log_score"] for r in rows) - result["held_log_score"]) < 1e-7
    output = []
    for dataset in sorted({membership[r["session_id"]] for r in rows}):
        current = [r for r in rows if membership[r["session_id"]] == dataset]
        old = {r["session_id"]: r for r in original[dataset]["evaluation"]}
        assert {r["session_id"] for r in current} == set(old)
        differences = [
            r["held_log_score"] - old[r["session_id"]]["held_log_score"] for r in current
        ]
        assert all(
            r["held_observations"] == old[r["session_id"]]["held_observations"] for r in current
        )
        output.append(
            {
                "dataset": dataset,
                "records": len(current),
                "held_log_score": sum(r["held_log_score"] for r in current),
                "held_delta_vs_original_panel": sum(differences),
                "positive_records": sum(d > 0 for d in differences),
                "held_observations": sum(r["held_observations"] for r in current),
                "record_deltas": [
                    {"session_id": r["session_id"], "delta": d}
                    for r, d in zip(current, differences, strict=True)
                ],
            }
        )
    return {"state": "returned", "datasets": output}


rows = []
for unit in plan["units"]:
    folder = HERE / unit["unit_id"]
    selection = load_selection(folder, "source")
    selected = selection["selected"]
    row = {
        "unit_id": unit["unit_id"],
        "source_datasets": unit["source_datasets"],
        "source_records": len(unit["session_ids"]),
        "planned_starts": len(unit["starts"]),
        "returned_starts": sum(r is not None for r in selection["runs"]),
        "successful_starts": sum(r is not None and r["success"] for r in selection["runs"]),
        "qualified_starts": sum(r is not None and r["qualified"] for r in selection["runs"]),
    }
    if selected is None:
        row["state"] = "no_successful_source_start"
        rows.append(row)
        continue
    assert selected["session_ids"] == unit["session_ids"]
    row.update(
        state="returned",
        qualified=selected["qualified"],
        horizontal_error_m=error(selected["estimate"]),
        estimate=selected["estimate"],
        max_abs_gradient=max(abs(v) for v in selected["gradient"]),
    )
    row["source_held"] = held_comparison(folder / "source_held/result.json", selected)
    points = [np.array(r["x"][:2]) for r in selection["runs"] if r is not None]
    row["maximum_start_separation_m"] = 1000 * max(
        np.linalg.norm(a - b) for a in points for b in points
    )
    if unit["excluded_dataset"] is not None:
        target = load_selection(folder, "target")
        t = target["selected"]
        row["excluded_dataset"] = unit["excluded_dataset"]
        row["target_timing_qualified"] = t is not None and t["qualified"]
        row["target_returned_starts"] = sum(r is not None for r in target["runs"])
        row["target_successful_starts"] = sum(
            r is not None and r["success"] for r in target["runs"]
        )
        row["target_qualified_starts"] = sum(
            r is not None and r["qualified"] for r in target["runs"]
        )
        if t is not None:
            assert t["x"][:2] == selected["x"][:2]
            assert t["session_ids"] == next(
                g["session_ids"]
                for g in plan["groups"]
                if g["dataset_id"] == unit["excluded_dataset"]
            )
            row["target_held"] = held_comparison(folder / "target_held/result.json", t)
    rows.append(row)
output = {
    "rows": rows,
    "original_panels": [
        {"dataset": d, "records": 8, "horizontal_error_m": error(r["estimate"])}
        for d, r in original.items()
    ],
    "coordinate_origin_error_m": error(
        dict(
            zip(
                ("latitude_deg", "longitude_deg"),
                plan["config"]["geographic_prior_center_deg"],
                strict=True,
            )
        )
    ),
    "audit": {
        "bindings": len(bindings),
        "geographic_checks": checks,
        "reference_sha256": reference_bindings,
    },
}
audit_path = HERE / "gradient-audit/result.json"
output["position_gradient_audit"] = (
    json.loads(audit_path.read_text()) if audit_path.exists() else {"state": "unavailable"}
)
with (HERE / "scores.json").open("x") as stream:
    json.dump(output, stream, indent=2, allow_nan=False)
print(json.dumps(output, indent=2))
