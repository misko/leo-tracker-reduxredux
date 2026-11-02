"""Postdecision independent geography arithmetic, no RF fitting or selection."""
import csv
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPORT = ROOT.parent
READINESS = REPORT.parent / "2026_11_01_promotion_readiness"
OLD = REPORT.parent / "2026_11_02_generalized_corrections"
METHODS = ("ALGO07", "A", "B", "Age3", "Age2")
ARMS = ("c0", "fitted_c")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def error_m(point):
    # Independently implement the documented east/north chart and spherical
    # distance, using atan2 rather than the reporter's arcsin expression.
    latitude = 37.906 + point[1] / 111.
    longitude = -122.545 + point[0] / (111.32 * math.cos(math.radians(37.906)))
    lat, lon, site_lat, site_lon = map(math.radians,
        (latitude, longitude, 37.849061591561885, -122.48574968092912))
    h = math.sin((lat - site_lat) / 2) ** 2 + math.cos(lat) * math.cos(site_lat) * math.sin((lon - site_lon) / 2) ** 2
    h = min(1., max(0., h))
    return 2 * 6371008.8 * math.atan2(math.sqrt(h), math.sqrt(1 - h))


def quantile(values, fraction):
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    low, high = math.floor(index), math.ceil(index)
    return ordered[low] + (index - low) * (ordered[high] - ordered[low])


def main():
    result_path, position_path, statistic_path = [REPORT / p for p in
        ("evaluation/results.json", "positions.csv", "statistics.csv")]
    results = read(result_path)
    audit = read(ROOT / "final_audit.json")
    require(audit["status"] == "passed" and audit["results_sha256"] == sha(result_path), "RF decision audit differs")
    binding = read(REPORT / "position_binding.json")
    require(binding["results_sha256"] == sha(result_path) and binding["audit_sha256"] == sha(ROOT / "final_audit.json"), "Postdecision position binding differs")
    records = {r["case"]: r for r in read(REPORT / "evaluation/rf_roster.json")["cases"]}
    decisions = {r["case"]: r for r in results["rows"]}
    previous = {(r["case"], r["arm"], r["method"]): r for r in csv.DictReader((OLD / "position_results.csv").open())}
    populations_path = READINESS / "population_audit.json"
    population = {r["case"]: r for r in read(populations_path)["outcomes"]}
    inputs, authorities, baseline = {}, {str(populations_path): sha(populations_path)}, {}
    pre_guard_differences = []
    for case, record in records.items():
        inputs[case] = read(record["input_path"])
        if case in population:
            authority = population[case]
        else:
            path = READINESS / ("ds24/candidate" if case.startswith("DS24") else "candidate") / case / "result.json"
            authority = read(path)
            authorities[str(path)] = sha(path)
        require(authority["selected"] == record["selected"], "Guarded baseline selection differs")
        for arm in ARMS:
            endpoint = authority["final"][arm]
            baseline[case, arm] = dict(endpoint, error_m=error_m(endpoint["x"]))
            require(abs(baseline[case, arm]["error_m"] - endpoint["error_m"]) < 1e-7, "Authoritative baseline geography differs")
            require(abs(endpoint["objective"] - record["baseline"][arm]["objective"]) < 1e-8 and endpoint["associated"] == record["baseline"][arm]["associated"], "Guarded baseline RF/coverage binding differs")
            require(abs(baseline[case, arm]["error_m"] - float(previous[case, arm, "ALGO07"]["error_m"])) < 1e-7, "Inherited comparator maps to a different endpoint")
            seed_error = error_m(inputs[case]["baseline_arms"][arm]["endpoint_east_north_km"])
            if abs(seed_error - baseline[case, arm]["error_m"]) > .02:
                pre_guard_differences.append(dict(case=case, arm=arm, seed_error_m=seed_error,
                    published_ALGO07_error_m=baseline[case, arm]["error_m"], guarded_selected=record["selected"]))
    rows = list(csv.DictReader(position_path.open()))
    keyed = {(r["case"], r["arm"], r["method"]): r for r in rows}
    require(len(rows) == len(keyed) == 205 * 2 * 5, "Position rows missing or duplicated")
    max_error_difference = 0.
    for case, record in records.items():
        for arm in ARMS:
            expected = dict(ALGO07=baseline[case, arm]["error_m"])
            for label in ("A", "B"):
                output = record["selected_" + label][arm]
                expected[label] = error_m(output["x"]) if output["source"] != "exact_saved_ALGO07" else expected["ALGO07"]
            for label in ("Age3", "Age2"):
                policy = decisions[case]["policies"][label]
                output = policy["selected_output"][arm]
                if not policy["accepted"]:
                    require(output == record["selected_A"][arm], "Age policy fallback is not exact A")
                else:
                    require(output["x"] == decisions[case]["raw_endpoints"][arm]["x"], "Age policy scored a different endpoint")
                expected[label] = error_m(output["x"]) if policy["accepted"] else expected["A"]
            for method in METHODS:
                row = keyed[case, arm, method]
                difference = abs(float(row["error_m"]) - expected[method])
                max_error_difference = max(max_error_difference, difference)
                require(difference < 1e-7, "Position error differs: " + str((case, arm, method)))
                require(row["dataset"] == record["dataset"] and int(row["associated_points"]) == baseline[case, arm]["associated"], "Cohort/coverage differs")
                for control in ("ALGO07", "A", "B"):
                    require(abs(float(row["change_vs_" + control + "_m"]) - (expected[method] - expected[control])) < 1e-7, "Position contrast differs")
                if method in ("Age3", "Age2"):
                    policy = decisions[case]["policies"][method]
                    require((row["accepted"] == "True") == policy["accepted"] and row["source"] == policy["selected_output"][arm]["source"], "Age reporting acceptance/source differs")
                else:
                    old = previous[case, arm, {"B": "A+B"}.get(method, method)]
                    require((row["accepted"] == "True") == (old["stage_accepted"] == "True") and row["source"] == old["output_source"], "Immutable method reporting differs")
    statistics = list(csv.DictReader(statistic_path.open()))
    require(len(statistics) == 60 and len({(r["scope"], r["arm"], r["method"]) for r in statistics}) == 60, "Statistics rows missing or duplicated")
    max_statistic_difference = 0.
    for statistic in statistics:
        subset = [r for r in rows if r["arm"] == statistic["arm"] and r["method"] == statistic["method"]
            and (statistic["scope"] == "ALL" or r["dataset"] == statistic["scope"])]
        errors = [float(r["error_m"]) for r in subset]
        changes = [float(r["change_vs_ALGO07_m"]) for r in subset]
        expected = dict(n=len(subset), mean_m=math.fsum(errors) / len(errors), median_m=quantile(errors, .5),
            p90_m=quantile(errors, .9), p95_m=quantile(errors, .95), max_m=max(errors),
            below500=sum(e < 500 for e in errors), improved_over50m=sum(d < -50 for d in changes),
            regressed_over50m=sum(d > 50 for d in changes), max_regression_m=max(0., max(changes)),
            associated_points=sum(int(r["associated_points"]) for r in subset))
        for key, value in expected.items():
            difference = abs(float(statistic[key]) - value)
            max_statistic_difference = max(max_statistic_difference, difference)
            require(difference < 1e-7, "Cohort arithmetic differs: " + str((statistic["scope"], statistic["arm"], statistic["method"], key)))
    summary = read(REPORT / "position_summary.json")
    require(summary["binding"] == binding and summary["policy_accepted"] == results["policy_accepted"], "Position summary authority/count differs")
    require(len(summary["statistics"]) == 60, "Summary statistics incomplete")
    for table, entry in zip(statistics, summary["statistics"]):
        require(all(table[k] == str(v) for k, v in entry.items()), "CSV/JSON statistic differs")
    packet = dict(status="passed", postdecision_GPS_reporting_only=True, no_fit=True,
        results_sha256=sha(result_path), positions_sha256=sha(position_path), statistics_sha256=sha(statistic_path),
        reporter_sha256=sha(REPORT / "report_positions.py"), auditor_sha256=sha(__file__),
        recordings=205, arm_method_cells=len(rows), statistics_rows=len(statistics),
        maximum_independent_error_difference_m=max_error_difference,
        maximum_independent_statistic_difference_m=max_statistic_difference,
        baseline_authority_sha256=authorities, seed_is_not_published_baseline=pre_guard_differences,
        policy_accepted=results["policy_accepted"],
        baseline_mapping="Published guarded ALGO07 final endpoints, including accepted repairs; raw input baseline_arms can be earlier seeds",
        exact_A_fallback_and_accepted_endpoint_scoring=True, all_cohort_statistics_verified=True)
    (ROOT / "position_reporting_audit.json").write_text(json.dumps(packet, indent=2, allow_nan=False) + "\n")
    print(json.dumps({k: v for k, v in packet.items() if k not in ("baseline_authority_sha256", "seed_is_not_published_baseline")}, indent=2))
    print("Earlier seed discrepancy arms:", len(pre_guard_differences), "cases:", sorted({r["case"] for r in pre_guard_differences}))


if __name__ == "__main__":
    main()
