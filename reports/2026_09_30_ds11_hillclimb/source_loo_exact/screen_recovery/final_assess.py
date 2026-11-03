"""Seal the full denominator, scoring geography only after eight selections."""
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics

HERE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify(row):
    for path, expected in row["sources"].items():
        assert digest(path) == expected, path


def geographic_outcome(plan, rows, sources):
    harness_path = HERE.parents[1] / "harness.py"
    spec = importlib.util.spec_from_file_location("recovery_geographic_harness", harness_path)
    harness = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(harness)
    sources[str(harness_path)] = digest(harness_path)
    for row, scan in zip(rows, plan["scans"], strict=True):
        assert row["index"] == scan["index"] and row["selectable"]
        for label, family in (("selected", row["selected_family"]), ("iid", "iid_t4_scale100")):
            path = Path(scan["endpoint_paths"][family])
            assert plan["sources"][str(path)] == digest(path)
            endpoint = json.loads(path.read_text())["selected"]
            assert endpoint["qualified"]
            seeds = [j["full_endpoint_x"] for j in plan["jobs"]
                     if j["index"] == row["index"] and j["family"] == family]
            assert seeds and all(seed == endpoint["x"] for seed in seeds)
            row[label + "_estimate_deg"] = endpoint["estimate_deg"]
            row[label + "_error_m"] = harness.distance(endpoint["estimate_deg"])
            sources[str(path)] = digest(path)
        row["improved"] = row["selected_error_m"] < row["iid_error_m"]
    def metrics(values):
        return dict(median_m=statistics.median(values), mean_m=statistics.mean(values),
                    p90_m=harness.percentile(values, .9), maximum_m=max(values),
                    sub_km=sum(v < 1000 for v in values))
    selected = metrics([r["selected_error_m"] for r in rows])
    iid = metrics([r["iid_error_m"] for r in rows])
    wins = sum(r["improved"] for r in rows)
    reduction = 1-selected["median_m"]/iid["median_m"]
    gate = plan["selection"]["geographic_gate"]
    passed = bool(wins >= gate["minimum_wins_over_iid"]
                  and reduction >= gate["minimum_median_error_reduction_fraction"]
                  and selected["p90_m"] <= iid["p90_m"])
    return dict(selected=selected, iid=iid, wins=wins, median_reduction_fraction=reduction,
                geographic_errors_evaluated=True, advancement_gate_passed=passed,
                reference_deg=list(harness.REFERENCE), reference_is_surveyed=False)


def main():
    plan_path = HERE / "plan.json"
    plan = json.loads(plan_path.read_text())
    verify(plan)
    sources = {str(plan_path): digest(plan_path), str(Path(__file__).resolve()): digest(__file__)}
    rows = []
    stopped = False
    for index in plan["screen_indices"]:
        path = HERE / "selections" / f"{index:02d}.json"
        if not path.exists():
            if not stopped:
                raise ValueError("screen is still incomplete; no outcome may be sealed")
            assert not list((HERE / "runs").glob(f"{index:02d}_*.receipt.json"))
            rows.append(dict(index=index, status="not_attempted_after_stop", selectable=False))
            continue
        assert not stopped
        selected = json.loads(path.read_text())
        assert selected["schema"] == "ds11-source-loo-recovery-screen-selection/v1"
        assert selected["index"] == index and selected["reference_used"] is False
        assert selected["sources"][str(plan_path)] == digest(plan_path)
        verify(selected)
        sources[str(path)] = digest(path)
        rows.append({k: selected[k] for k in (
            "index", "selectable", "selected_family", "planned_folds", "qualified_folds", "cached_folds")})
        rows[-1]["status"] = "selectable" if selected["selectable"] else "unselectable"
        stopped = not selected["selectable"]
    assert len(rows) == 8
    outcome = dict(schema="ds11-source-loo-recovery-screen-outcome/v1",
        screen_denominator=8, selectable_scans=sum(r["selectable"] for r in rows),
        geographic_errors_evaluated=False, advancement_gate_passed=False,
        scans=rows, sources=sources)
    if not stopped:
        outcome.update(geographic_outcome(plan, rows, sources))
    with (HERE / "outcome.json").open("x") as stream:
        json.dump(outcome, stream, indent=2, allow_nan=False)
    print(json.dumps({k:v for k,v in outcome.items() if k not in ("sources", "scans")}))


if __name__ == "__main__":
    main()
