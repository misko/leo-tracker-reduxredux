"""Recover per-recording errors, check source identities, and score the fixed comparison."""

import csv
import hashlib
import importlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

import numpy as np

from .run_v5_panel import ARCHIVE, BLIND, HERE, OUTPUT, ROLES, manifest, published_worker

field_score = importlib.import_module("reports.2026_11_18_blind_regional_receiver.evaluation.score")
TRUTH_DIRS = dict(recorded="recorded_private", field="field_private",
                  synthetic="holdout_private", field2="field2_private")
NAMES = dict(recorded="DS29", field="StarLoc", synthetic="Synthetic", field2="Altrincham")
ARMS = ["c0", "fitted_c"]


def read(path):
    return json.loads(path.read_bytes())


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def quantiles(values):
    names = ("min", "mean", "p10", "p25", "p50", "p75", "p90", "p95", "p99", "max")
    if not values:
        return {"n": 0, **dict.fromkeys(names)}
    q = np.quantile(values, [.1, .25, .5, .75, .9, .95, .99], method="linear")
    return {"n": len(values), **dict(zip(names, [min(values), mean(values), *q, max(values)],
                                         strict=True))}


def row(panel, case, condition, method, arm, status, point, truth, **extra):
    if point is not None:
        if status not in ("fix", "estimate") or len(point) != 2:
            raise ValueError("invalid endpoint or status")
        error = field_score.distance_km(tuple(point), tuple(truth))
    else:
        if status in ("fix", "estimate"):
            raise ValueError("coordinate missing from successful estimate")
        error = None
    return dict(panel=panel, case=case, condition=condition, method=method, arm=arm,
                status=status, latitude_deg=point[0] if point is not None else None,
                longitude_deg=point[1] if point is not None else None, error_km=error, **extra)


def grid_rows(panel, case, condition, mode, pred, truth, **audit):
    for forced in [False, True]:
        key = "best_latlon" if forced else "latlon"
        point = pred[key]
        region = pred["best_region" if forced else "region_id"]
        correct = None
        if point is not None and condition == "present":
            correct = region == audit.get("true_region")
        status = ("estimate" if point is not None else "no_estimate") if forced else pred["status"]
        yield row(panel, case, condition, f"grid_{'forced_' if forced else ''}{mode}",
                  "shape", status, point, truth, reason=pred["reason"], wall_s=pred["wall_s"],
                  region_id=region, correct_region=correct, **audit)


def v5_rows(panel, case, role, base, truth, member, policy, source_digest, common_residuals):
    execution = read(base / (role + "-execution.json"))
    status = execution["status"]
    worker_status = dict(worker_status=status, native_sha256=member.get("input_sha256"),
                         worker_request_sha256=execution["request_sha256"])
    if status == "complete":
        worker = execution["worker"]
        assert worker["policy"] == policy and worker["role"] == role
        assert worker["source_sha256"] == source_digest
        assert worker["request_sha256"] == execution["request_sha256"]
        req = read(base / role / "experimental-request.json")
        assert req["job"]["evaluation_reference"] is None
        assert req["job"]["native_input"]["sha256"] == member["input_sha256"]
        assert req["job"]["identity"]["session_id"] == member["session_id"]
        assert req["causal_snapshots"] == member["causal_snapshots"]
        # The original helper compares the same named arm from two prediction-row sets.
        # Supply the fitted rows on its right side to compare calibration at fixed IDs.
        fitted = {"prediction_rows": {"c0": worker["prediction_rows"]["fitted_c"]}}
        matched = common_residuals(worker, fitted, "c0")
        matched_rms = {"c0": matched["baseline_rms_hz"], "fitted_c": matched["candidate_rms_hz"]}
        for arm in ARMS:
            a = worker["arms"][arm]
            yield row(panel, case, "present", role, arm, "fix", a["endpoint_latlon"], truth,
                      rms_hz=a["residual_rms_hz"], frequency_score=a["frequency_score"],
                      matched_rms_hz=matched_rms[arm], matched_observations=matched["count"],
                      wall_s=execution["process"]["wall_seconds"], **worker_status)
    else:
        for arm in ARMS:
            yield row(panel, case, "present", role, arm, status, None, truth,
                      wall_s=execution.get("process", {}).get("wall_seconds"), **worker_status)


def summarize_group(rows):
    errors = [r["error_km"] for r in rows if r["error_km"] is not None]
    regions = [r["correct_region"] for r in rows if r.get("correct_region") is not None]
    return dict(attempts=len(rows), numerical_outputs=len(errors),
                statuses=dict(Counter(r["status"] for r in rows)), error_km=quantiles(errors),
                observed_wrong_regions=regions.count(False) if regions else None,
                within_km={str(k): sum(e <= k for e in errors) for k in [0.5, 1, 2, 3, 5, 10]},
                wall_s=quantiles([r["wall_s"] for r in rows if r.get("wall_s") is not None]),
                rf_rms_hz=quantiles([r["rms_hz"] for r in rows if r.get("rms_hz") is not None]))


def paired(rows, method, arm, other, other_arm):
    def keyrows(m, a):
        return {r["case"]: r for r in rows if r["method"] == m and r["arm"] == a
                and r["condition"] == "present" and r["error_km"] is not None}

    left, right = keyrows(method, arm), keyrows(other, other_arm)
    ids = sorted(left.keys() & right.keys())
    delta = [right[k]["error_km"] - left[k]["error_km"] for k in ids]
    rms = [right[k]["rms_hz"] - left[k]["rms_hz"] for k in ids
           if left[k].get("rms_hz") is not None and right[k].get("rms_hz") is not None]
    matched_rms = []
    if method == other and (arm, other_arm) == ("c0", "fitted_c"):
        matched_rms = [right[k]["matched_rms_hz"] - left[k]["matched_rms_hz"] for k in ids
                       if left[k].get("matched_rms_hz") is not None]
    return dict(common_cases=ids, n=len(ids), left_km=quantiles([left[k]["error_km"] for k in ids]),
                right_km=quantiles([right[k]["error_km"] for k in ids]),
                right_minus_left_km=quantiles(delta), right_closer=sum(d < -1e-9 for d in delta),
                tied=sum(abs(d) <= 1e-9 for d in delta),
                paired_selected_rms_change_hz=quantiles(rms),
                paired_same_observation_rms_change_hz=quantiles(matched_rms))


def evaluate_group(rows):
    groups = defaultdict(list)
    for r in rows:
        groups[r["condition"], r["method"], r["arm"]].append(r)
    metrics = {"/".join(k): summarize_group(group) for k, group in groups.items()}
    paired_results = {}
    for method in ROLES:
        if ("present", method, "fitted_c") not in groups:
            continue
        paired_results[f"{method}/c0-to-fitted"] = paired(rows, method, "c0", method, "fitted_c")
        for other in ["grid_four", "grid_forced_four", "grid_one", "grid_forced_one"]:
            if ("present", other, "shape") in groups:
                pair = paired(rows, method, "fitted_c", other, "shape")
                paired_results[f"{method}/{other}"] = pair
        if method != "baseline":
            paired_results[f"baseline/{method}"] = paired(rows, "baseline", "fitted_c", method,
                                                         "fitted_c")
    return {"distributions": metrics, "paired": paired_results}


def blind_rows(ds29_map):
    lock = read(BLIND / "locks/prediction-lock.json")
    for p, private in TRUTH_DIRS.items():
        name = NAMES[p]
        path = BLIND / "predictions" / (p + ".json")
        assert file_sha(path) == lock["sha256"][path.name]
        committed = read(BLIND / "locks" / (p + ".json"))
        truth_path = BLIND / private / "truth.json"
        assert file_sha(truth_path) == committed["truth_sha256"]
        truth = {r["id"]: r for r in read(truth_path)["cases"]}
        with (BLIND / "results" / p / "per_query.csv").open(newline="") as stream:
            scored = {r["id"]: r for r in csv.DictReader(stream)}
        pred = read(path)["cases"]
        assert set(truth) == set(scored) == {r["id"] for r in pred}
        for obs in pred:
            k = obs["id"]
            target, original = truth[k], scored[k]
            case = ds29_map[original["observations_sha256"]] if p == "recorded" else target["pair"]
            generated = grid_rows(name, case, target["condition"], "four", obs, target["latlon"],
                                  query_id=k, site_group=target["site_group"],
                                  true_region=target["true_region"],
                                  source="locked_blind",
                                  observation_sha256=original["observations_sha256"])
            for r in generated:
                forced = r["method"] == "grid_forced_four"
                col = "forced_rf_error_km" if forced else "receiver_error_km"
                published = original[col]
                assert (r["error_km"] is None and not published) or math.isclose(
                    r["error_km"], float(published), rel_tol=1e-10, abs_tol=1e-10)
                yield r


def write_tables(summary, groups):
    with (HERE / "distributions.csv").open("w", newline="") as stream:
        out = csv.writer(stream)
        quantiles_km = ["min", "mean", "p10", "p25", "p50", "p75", "p90", "p95", "p99", "max"]
        out.writerow(["cohort", "condition", "method", "arm", "attempts", "coordinates",
                      *[v + "_km" for v in quantiles_km], "within_1km", "within_2km", "within_5km"])
        for panel in groups:
            for key, obj in summary[panel]["distributions"].items():
                out.writerow([panel, *key.split("/"), obj["attempts"], obj["numerical_outputs"],
                              *[obj["error_km"][v] for v in quantiles_km],
                              *[obj["within_km"][v] for v in ("1", "2", "5")]])
    with (HERE / "eight-recording-panels.csv").open("w", newline="") as stream:
        out = csv.writer(stream)
        methods = [*ROLES, "grid_four", "grid_forced_four", "grid_one", "grid_forced_one"]
        out.writerow(["cohort", "case", "calibration", *[m + "_error_km" for m in methods]])
        for panel in ["DS29", "DS26_prior8"]:
            per_case = defaultdict(dict)
            for r in groups[panel]:
                if r["condition"] == "present":
                    per_case[r["case"]][r["method"], r["arm"]] = r
            for case, indexed in sorted(per_case.items()):
                for arm in ARMS:
                    results = [indexed[m, arm if m in ROLES else "shape"] for m in methods]
                    out.writerow([panel, case, arm, *[r["error_km"] if r["error_km"] is not None
                                                     else r["status"] for r in results]])


def main():
    cfg = read(ARCHIVE / "plans/science.json")
    common_residuals = published_worker().common_residuals
    ds26, ds29 = cfg["cohorts"]["DS26"], manifest()["cohorts"]["DS29"]
    reference_file = Path(ds29["snapshot"]) / "evaluation-references.json"
    ds29 = dict(ds29, references=read(reference_file))
    original = read(ARCHIVE / "results/repeat-comparison.json")
    common = set(original["same_successful_cases"])
    chosen = read(BLIND / "recorded_private/provenance.json")["observations"]
    by_observation = {r["observation_sha256"]: r["dataset_label"] for r in chosen}
    for r in read(BLIND / "recorded_private/truth.json")["cases"]:
        q = read(BLIND / "public_recorded/queries" / (r["id"] + ".json"))
        ref = ds29["references"][by_observation[q["observation"]]]
        assert r["latlon"] == [ref["latitude_deg"], ref["longitude_deg"]]
    rows = list(blind_rows(by_observation))
    old = read(BLIND.parent / "2026_11_18_embedded_prototypes/panel.json")["cases"]
    earlier_ds29 = Path("/srv/bulk/leo-dev/ds26-ds29-evaluation-20261113/ds29-bulk-pairs-001")
    crosscheck = []
    for panel, cohort, base in [("DS26", ds26, ARCHIVE / "results"), ("DS29", ds29, OUTPUT)]:
        for member in cohort["members"]:
            case = member["dataset_label"]
            if panel == "DS29" and case not in by_observation.values():
                continue
            ref = cohort["references"][case]
            truth = [ref["latitude_deg"], ref["longitude_deg"]]
            for role in ROLES:
                new = list(v5_rows(
                    panel, case, role, base / (case + "-r0"), truth, member,
                    cfg["policies"][role], cfg["source"]["sha256"], common_residuals,
                ))
                for r in new:
                    r["source"] = "published_repeat_0" if panel == "DS26" else "frozen_v5_replay"
                rows.extend(new)
                if panel == "DS29" and role == "baseline":
                    hist = read(earlier_ds29 / (case + "-r0/candidate/report.json"))["results"][0]
                    assert "leo.cli.algo07v5" in hist["command"]
                    assert hist["input_sha256"] == member["input_sha256"]
                    assert hist["reference"] == ref
                    for r in new:
                        a = r["arm"]
                        crosscheck.append(dict(case=case, arm=a, status=r["status"],
                                               earlier_error_km=hist["arms"][a]["gps_error_km"],
                                               rerun_error_km=r["error_km"]))
            result = read(HERE / "prototype" / (case + ".json"))
            assert result["case"] == case
            for mode in result["offers"]:
                if result["status"] == "input_unavailable":
                    for m in [f"grid_{mode}", f"grid_forced_{mode}"]:
                        rows.append(row(panel, case, "present", m, "shape", result["status"],
                                        None, truth, reason=result["reason"]))
                else:
                    assert result["provenance"]["native"] == member["input_sha256"]
                    rows.extend(grid_rows(panel, case, "present", mode, result["predictions"][mode],
                                          truth, source="frozen_grid_replay",
                                          true_region="original",
                                          observation_sha256=result["observation"],
                                          native_sha256=member["input_sha256"]))
    assert len({(r["panel"], r["case"], r["condition"], r["method"], r["arm"])
                for r in rows}) == len(rows)
    groups = {p: [r for r in rows if r["panel"] == p]
              for p in ["DS26", "DS29", "StarLoc", "Synthetic", "Altrincham"]}
    groups["DS26_common127"] = [r for r in groups["DS26"] if r["case"] in common]
    groups["DS26_prior8"] = [r for r in groups["DS26"] if r["case"] in old]
    assert len(common) == 127 and len(by_observation) == len(old) == 8
    summary = {k: evaluate_group(v) for k, v in groups.items()}
    assert ds26["template"]["search_center"] == ds29["template"]["search_center"]
    center = ds26["template"]["search_center"]
    for key, cohort in [("DS26", ds26), ("DS26_common127", ds26),
                        ("DS26_prior8", ds26), ("DS29", ds29)]:
        ids = sorted({r["case"] for r in groups[key]})
        refs = [cohort["references"][k] for k in ids]
        summary[key]["original_tile_center_only_km"] = quantiles([
            field_score.distance_km(center, [r["latitude_deg"], r["longitude_deg"]]) for r in refs
        ])
    for role in ROLES:
        for arm in ARMS:
            published = original["summaries"][f"same_successful_cohort/{role}/r0"]["arms"][arm]
            s = summary["DS26_common127"]["distributions"][f"present/{role}/{arm}"]
            for dest, source in [("error_km", "gps_error_km"), ("rf_rms_hz", "residual_rms_hz")]:
                values = published[source]
                for q in ["mean", "p50", "p90", "p95", "p99", "max"]:
                    field = "median" if q == "p50" else q
                    assert math.isclose(s[dest][q], values[field], rel_tol=1e-9)
                    repeat = original["summaries"][f"same_successful_cohort/{role}/r1"]["arms"][arm]
                    assert math.isclose(values[field], repeat[source][field], rel_tol=1e-9)
    summary["DS29"]["historical_no_repair_crosscheck"] = crosscheck
    write_tables(summary, groups)
    summary["provenance"] = {
        "source_sha256": cfg["source"]["sha256"], "original_repeat_table_sha256":
        file_sha(ARCHIVE / "results/repeat-comparison.json"),
        "engine_sha256": read(BLIND / "locks/engine.json")["sha256"],
        "blind_prediction_lock_sha256": file_sha(BLIND / "locks/prediction-lock.json"),
        "ds29_evaluation_references_sha256": file_sha(reference_file),
        "design_sha256": file_sha(HERE / "comparison-design.json"),
        "original_repeat_statuses": original["statuses"],
    }
    for r in rows:
        if r["panel"] == "DS26":
            r["in_original_127"] = int(r["case"] in common)
            r["in_prior_ds26_eight"] = int(r["case"] in old)
    rows.sort(key=lambda r: (r["panel"], r["case"], r["condition"], r["method"], r["arm"]))
    with (HERE / "sample-errors.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(dict.fromkeys(k for r in rows for k in r)))
        writer.writeheader()
        writer.writerows(rows)
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    print(f"Verified and scored {len(rows)} recording, configuration and calibration rows.")


if __name__ == "__main__":
    main()
