"""Reduce only the two frozen original-format raw physical comparisons."""

import argparse
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
from statistics import median
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
CASES = {"DS30-0107": "withheld", "DS30-0016": "complete"}
MODES = ("candidate", "stock")
ARMS = {"c0", "fitted_c"}
BOUNDARIES = ("cpu_s", "elapsed_s")


def enrolled():
    from eight_ms_0107_pair import archived
    from history_risk_0016_raw import references
    from history_risk_0107_raw import CONTROL

    small = archived(CONTROL)["documents"]
    old, small_runs = small["binding.json"], small["post-verification.json"]["modes"]
    short = small_runs["candidate"]["bootstrap"]
    small_req = dict(recording=old["recording"], session=old["session"], authority=old["signed_raw_authority"],
        inventory=short["receiver_audit"]["input_manifest"], cutoff_utc_ns=old["expected_causal_cutoff_utc_ns"],
        offer_sha256=old["offer_sha256"], archive={"snapshots_sha256": old["archive"]},
        native=small_runs["candidate"]["native_sha256"], detector=short["detector_recipe_sha256"])
    weak_req, weak, stock, _ = references()
    return {"DS30-0107": dict(request=small_req, stock=small_runs["stock"], issued=29, admitted=27, installed=old["named"]),
            "DS30-0016": dict(request=weak_req, stock=stock, issued=808, admitted=713, installed=weak["stock"])}


def finite_positive(value):
    return type(value) in (int, float) and isfinite(value) and value > 0


def raw_rows(data, expected, options_for):
    case, admission = data["case"], data["admission"]
    req, ref = admission["request"], expected["request"]
    base, runs, logs = expected["stock"], data["runs"], data["measured_exits"]
    if (tuple(admission["order"]) != MODES or set(runs) != set(MODES) or set(logs) != set(MODES)
            or not data["same_opportunities"] or admission["stock"] != expected["installed"]
            or any(req[key] != value for key, value in ref.items() if key not in ("archive", "saved_inventory", "packet"))
            or req["archive"]["snapshots_sha256"] != ref["archive"]["snapshots_sha256"]
            or not finite_positive(admission["setup_wall_s"]) or admission["conditioning_bytes"] or admission["original_backing_bytes"]
            or options_for(admission["commands"]["candidate"]) != admission["active_options"]
            or not admission["active_options"]["history_risk_route"]
            or not finite_positive(logs["candidate"]["clock"]["started_unix_ns"])
            or logs["candidate"]["clock"]["started_unix_ns"] >= logs["stock"]["clock"]["started_unix_ns"]
            or not isinstance(data["pre_score_sha256"], str) or len(data["pre_score_sha256"]) != 64):
        raise ValueError(f"{case} did not use the frozen original raw comparison")
    results = {}
    for mode in MODES:
        scope, run = logs[mode], runs[mode]
        measurement = scope["clock"]
        science, expected_native = run["science"], req["native"] if mode == "candidate" else base["native_sha256"]
        receipt = science["receipt"]
        argv = scope["command"]
        expected_args = {"--recording": req["recording"], "--archive": req["archive"]["root"], "--region": req["region"]}
        phases = run["phases"]
        if (run["process"] != scope or argv != admission["commands"][mode]
                or any(argv[argv.index(flag)+1] != value for flag, value in expected_args.items())
                or measurement["exit_code"] != 0 or any(not finite_positive(measurement[key]) for key in BOUNDARIES)
                or any(not cache["members"] or cache["unavailable"] or cache["cached_pages"] != cache["observed_file_pages"]
                       for at in ("cache_before", "cache_after") for cache in (scope[at], scope[at]["index_cache"]))
                or run["digest"] != expected_native or science["raw_authority"] != req["authority"]
                or run["opportunities"] != base["opportunities"] or set(science["arms"]) != ARMS
                or receipt["region"] != base["science"]["receipt"]["region"] or receipt["session_id"] != req["session"]
                or receipt["window_count"] != expected["issued"] or receipt["counts"]["processed"] != expected["admitted"]
                or receipt["counts"]["invalid_capture"] != expected["issued"]-expected["admitted"]
                or mode == "candidate" and (phases is None or not all(
                    finite_positive(phases["authenticated_raw_acquisition"][key])
                    and phases["authenticated_raw_acquisition"][key] <= measurement[key] for key in BOUNDARIES))):
            raise ValueError(f"{case} {mode} lacks a matched paid raw boundary or signed outcome")
        fixed = receipt["decision"] == "complete"
        if (receipt["decision"] not in CASES.values() or len(run["figures"]) != (8 if fixed else 0)
                or bool(run["sidecars"]) != fixed or any(bool(row["latlon"]) != fixed for row in science["arms"].values())):
            raise ValueError(f"{case} {mode} published incompatible science and artifacts")
        errors = data.get("geographical_and_rf", {}).get("runs", {}).get(mode, {}).get("horizontal_error_km", {})
        arms = {}
        for arm, row in science["arms"].items():
            error, rms = errors.get(arm), row.get("rf_rms_hz")
            if (fixed and (error is None or not isfinite(error) or error < 0 or rms is None or not isfinite(rms) or rms < 0)
                    or not fixed and (error is not None or rms is not None)):
                raise ValueError(f"{case} {mode} requires both scientific-arm results or nulls")
            arms[arm] = dict(position=row["latlon"], horizontal_error_km=error, conditional_rf_rms_hz=rms)
        results[mode] = dict(decision=receipt["decision"], reason=science["reason"], arms=arms, native=run["digest"],
                             clock={key: measurement[key] for key in BOUNDARIES})
    return results


def reduce(data, expected, options_for):
    if len(data) != len(CASES) or {row["case"] for row in data} != set(CASES):
        raise ValueError("Exactly the two prospectively enrolled raw results are required")
    rows = {row["case"]: raw_rows(row, expected[row["case"]], options_for) for row in data}
    a, b = (row["admission"] for row in data)
    for key in ("adapters", "candidate_libraries", "active_options", "machine", "stock"):
        if a[key] != b[key]:
            raise ValueError(f"The two original-format comparisons differ in {key}")
    timings = {}
    for field in BOUNDARIES:
        ratios = {case: arms["candidate"]["clock"][field]/arms["stock"]["clock"][field] for case, arms in rows.items()}
        totals = {mode: sum(arms[mode]["clock"][field] for arms in rows.values()) for mode in MODES}
        timings[field] = dict(per_case_ratios=ratios, totals=totals, median_ratio=median(ratios.values()),
                              summed_ratio=totals["candidate"]/totals["stock"])
    wall = timings["elapsed_s"]
    correct = {mode: sum(rows[case][mode]["decision"] == expected for case, expected in CASES.items()) for mode in MODES}
    decisions = {mode: dict(complete=sum(arms[mode]["decision"] == "complete" for arms in rows.values()),
                            withheld=sum(arms[mode]["decision"] == "withheld" for arms in rows.values()),
                            correct=correct[mode]) for mode in MODES}
    gates = {label: dict(median=wall["median_ratio"] <= target, summed=wall["summed_ratio"] <= target,
                         both_timings_and_decisions=max(wall["median_ratio"], wall["summed_ratio"]) <= target
                         and all(count == len(CASES) for count in correct.values()))
             for label, target in (("2x", .50), ("1.6x", .625))}
    return dict(cases=rows, timing=timings, gates=gates, decisions=decisions,
                offline_setup={row["case"]: row["admission"]["setup_wall_s"] for row in data},
                pre_score={row["case"]: row["pre_score_sha256"] for row in data})


if __name__ == "__main__":
    from history_risk_0016_raw import route_options

    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("results", type=Path, nargs=2)
    opts = command.parse_args()
    bodies = [file.read_bytes() for file in opts.results]
    result = reduce([json.loads(body) for body in bodies], enrolled(), route_options)
    result["inputs"] = {str(path): sha256(body).hexdigest() for path, body in zip(opts.results, bodies, strict=True)}
    print(json.dumps(result, indent=2, allow_nan=False))
