import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent


def read(path):
    return json.loads(path.read_text())


def distance(point):
    lat, lon = map(math.radians, point)
    rlat, rlon = map(math.radians, (37.849056280893684, -122.48575489722863))
    a = math.sin((lat - rlat) / 2) ** 2 + math.cos(lat) * math.cos(rlat) * math.sin((lon - rlon) / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(min(1, a)))


def main():
    exposure = []
    exposure_hashes = {}
    inventory_path = REPORTS / "2026_09_28_full_manifest_inputs/checkpoints/09-full-ready/panel-inputs.json"
    inventory = read(inventory_path)
    exposure_hashes[str(inventory_path.relative_to(REPORTS))] = hashlib.sha256(inventory_path.read_bytes()).hexdigest()
    for ds, folder in [("DS7", "2026_09_28_ds7_full_shared"), ("DS8", "2026_09_29_ds8_full_shared"), ("DS9", "2026_09_29_ds9_full_shared")]:
        group = next(g for g in inventory["groups"] if g["dataset_id"] == ds)
        plan_path, scores_path = REPORTS / folder / "plan.json", REPORTS / folder / "scores.json"
        plan, scores = read(plan_path), read(scores_path)
        row = next(r for r in scores["rows"] if r["dataset"] == ds)
        selected = row["selected"]
        expected = set(group["session_ids"])
        assert expected == {r["session_id"] for r in plan["membership"][ds]} == set(selected["session_ids"])
        assert len(selected["session_ids"]) == len(expected)
        assert len(selected["x"]) == len(expected) + 2
        assert selected["qualified"] and selected["success"] and scores["execution_bindings_verified"] > 0
        for path in (plan_path, scores_path):
            exposure_hashes[str(path.relative_to(REPORTS))] = hashlib.sha256(path.read_bytes()).hexdigest()
        exposure.append(dict(dataset=ds, total_scans=len(expected), previously_fitted=len(expected), not_previously_fitted=0, evidence=folder))
    rows = []
    for ds in ("DS7", "DS8", "DS9"):
        result = read(HERE / f"{ds}.json")
        assert read(HERE / f"{ds}.receipt.json")["exit_code"] == 0
        assert result["selected"]["qualified"]
        assert all(t["score"]["qualified"] for t in result["targets"])
        prior = read(REPORTS / f"2026_09_29_prefix_score_selection/{ds}.json")
        changes = {arm: [t["score"]["log_score"] - t["prior_scores"][arm]["log_score"] for t in result["targets"]] for arm in ("prefix8", "prefix12", "selected8")}
        rows.append(dict(dataset=ds, balanced_error_m=distance(result["selected"]["estimate_deg"]), score_selected_error_m=distance(prior["reduced"]["selected"]["estimate_deg"]), target_count=len(result["targets"]), differences={k: sum(v) for k, v in changes.items()}, per_target_differences=changes, wins={k: sum(x > 0 for x in v) for k, v in changes.items()}, qualified_starts=sum(s["qualified"] for s in result["starts"]), max_quadrature_difference=max(t["score"]["quadrature_difference"] for t in result["targets"]), elapsed_seconds=result["elapsed_seconds"]))
    with (HERE / "summary.json").open("x") as out:
        json.dump(dict(rows=rows, exposure=exposure, exposure_source_sha256=exposure_hashes), out, indent=2)
    print(json.dumps(dict(rows=rows, exposure=exposure), indent=2))


if __name__ == "__main__":
    main()
