"""Replay the clipped-face rule on sealed development and held public offers."""

import argparse
from math import cos, radians, ulp
from pathlib import Path
from time import process_time_ns

from aperture_trial import ARMS, read, write
from geographic_peak import frozen_json
from geographic_peak_score import (
    ARCHIVED,
    EDGE_PIN,
    INDIA_PIN,
    MEASUREMENTS,
    MIRRORS_PIN,
    RECORDINGS,
    file_sha,
    references,
)

from leo.contracts.digests import canonical_digest
from tools.pipeline_eval.variants.experimental import local_exterior_descent as descent
from tools.pipeline_eval.variants.experimental.regional_bound_guard import bound_arms
from tools.pipeline_eval.variants.experimental.regional_veto_short_circuit import (
    evaluate_terminal,
)

HERE = Path(__file__).resolve().parent
REGIONAL = HERE.parent / "regional-release"
PREDICTIONS_PIN = "46e8925aad5b047b89f57b95d22581a5eca4dfc52f3196790154c01bdc340549"
ARCHIVE_PIN = "735553ef3b9287884f6473bfc78bd8740e45c23927c79c56d95b0ba53376bb4a"
GRAPH_PIN = "a90ecb4da3475f9a332ad09c3a9a1682e2af0d128669d488088fbfb31a0544bd"
WORK = Path("/tmp/leo-regional-qZJKBw4W/outputs/blind/fast-scan-automatic-work")
BENCH = Path("/tmp/leo-algo08v2-2x-bench")


def endpoints_from_receipt(offer, arms):
    """Recover a serialized local bound within float-coordinate round-off only."""
    result = {}
    center_lat, center_lon = offer["center"]
    half = offer["width_km"] / 2
    for arm in ARMS:
        lat, lon = arms[arm]["latlon"]
        local = []
        for coordinate, origin, scale in (
            (lon, center_lon, 111.32 * cos(radians(center_lat))), (lat, center_lat, 111.)
        ):
            value = (coordinate - origin) * scale
            tolerance = 4 * scale * max(ulp(coordinate), ulp(origin)) + 4 * ulp(half)
            if abs(abs(value) - half) <= tolerance:
                value = half if value >= 0 else -half
            local.append(value)
        result[arm] = local
    return result


def carrier_record(document):
    from leo.analysis.localization_v3.tracks import winning_observations

    rows, meta = winning_observations(document)
    clock_keys = ("anchor_utc_ns", "causal_cutoff_utc_ns", "utc_half_width_s")
    geometry = {key: meta[key] for key in clock_keys}
    carriers = [{key: value for key, value in row.items() if key != "fractional_margin"}
                for row in rows]
    return carriers, geometry


def original_release_binding(site, offer, prediction, native_sha):
    path = WORK / prediction["run_id"] / "terminal.json"
    terminal = frozen_json(path, prediction["terminal_sha256"].removeprefix("sha256:"))
    if (
        terminal["region"] != offer or terminal["session_id"] != prediction["session_id"]
        or terminal["decision"] != "ok" or terminal["arms"] != prediction["arms"]
    ):
        raise ValueError("Held scored map and released terminal do not bind the same offer")
    original_doc, = [
        candidate for candidate in WORK.glob("*/detections.json")
        if file_sha(candidate) == terminal["native_sha256"].removeprefix("sha256:")
    ]
    scored_doc, = (BENCH / f"covariance-{site}-inside/baseline/fast-scan-automatic-work").glob(
        "*/detections.json"
    )
    evidence = carrier_record(frozen_json(scored_doc, native_sha))
    if evidence != carrier_record(read(original_doc)):
        raise ValueError("Held map and original terminal do not share observed Graph carrier inputs")
    return {
        "terminal_sha256": prediction["terminal_sha256"], "terminal_native": terminal["native_sha256"],
        "measured_carriers_sha256": canonical_digest(evidence), "scored_native": native_sha,
        "exact_document_match": terminal["native_sha256"] == "sha256:" + native_sha,
    }


def replay(site, name, offer, points, arms, identity, old_full_probe_cpu):
    width = offer["width_km"]
    endpoints = endpoints_from_receipt(offer, arms)
    cache = {}

    def scored(point):
        key = tuple(point["xy_km"])
        return cache.setdefault(key, point["receiver_scores"])

    started = process_time_ns()
    if bound_arms(endpoints, width):
        far = evaluate_terminal(points, width, scored)
    else:
        far = {"would_withhold": False, "stop": "no_clipped_arm", "probes_evaluated": 0}
    far_cpu = (process_time_ns() - started) / 1e9
    before = len(cache)
    started = process_time_ns()
    near = (
        {"would_withhold": False, "stop": "already_withheld_far", "probes_evaluated": 0}
        if far["would_withhold"]
        else descent.evaluate(endpoints, width, points, scored)
    )
    near_cpu = (process_time_ns() - started) / 1e9
    return {
        "site": site, "name": name, "offer": offer, "identity": identity,
        "arms": arms, "endpoints_km": endpoints, "map_sha256": canonical_digest(points),
        "stock_far": far, "near": near, "would_withhold": far["would_withhold"] or near["would_withhold"],
        "distinct_stock_scores": before, "additional_scores": len(cache) - before,
        "stock_readout_cpu_s": far_cpu, "added_readout_cpu_s": near_cpu,
        "archived_complete_map_cpu_s": old_full_probe_cpu,
    }


def run(output):
    india = frozen_json(MEASUREMENTS / "india-regional-diagnostic.json.gz", INDIA_PIN)["runs"]
    mirrors = frozen_json(ARCHIVED / "region-mirrors.json.gz", MIRRORS_PIN)
    edges = frozen_json(ARCHIVED / "edge-solvers.json.gz", EDGE_PIN)
    control = frozen_json(ARCHIVED / "graph-canonical-alias-south-solver.json", GRAPH_PIN)
    maps = frozen_json(ARCHIVED / "regional-reassignment.json.gz", ARCHIVE_PIN)
    predictions = frozen_json(REGIONAL / "predictions.json", PREDICTIONS_PIN)["rows"]
    fits = []
    for name in ("matched-tile", "omitted-tile"):
        row = india[name]["stock"]
        identity = row["identity"]
        fits.append(replay("india", name, identity["offer"], row["full_diagnostic"]["points"],
                           row["arms"], identity, row["diagnostic_clocks"]["prepared"]["cpu_s"]))
    for site in ("north", "south"):
        for name in ("inside", "outside"):
            map_record = mirrors["sites"][site][name]
            offer = map_record["offer"]
            if name == "outside" and site == "south":
                saved = control["cases"]["outside"]
                arms = saved["runs"]["reference"]["arms"]
                saved_offer, source = saved["region"], control["native_sha256"]
                pin = GRAPH_PIN
            else:
                saved = (edges[f"{site}-solver.json"] if name == "inside"
                         else mirrors["north_stock_position"])
                arms = saved["decision"]["arms"]
                saved_offer, source = saved["region"], saved["native_sha256"]
                pin = EDGE_PIN if name == "inside" else MIRRORS_PIN
            if saved_offer != offer or source.removeprefix("sha256:") != map_record["native_sha256"]:
                raise ValueError("Mirror map and fit do not bind identical detections")
            identity = {
                "native_sha256": source, "fit_source_sha256": pin, "map_source_sha256": MIRRORS_PIN,
            }
            fits.append(replay(site, name, offer, map_record["points"], arms, identity,
                               map_record["cpu_s"]["probes"]))
        for name in ("containing", "omitted", "far"):
            map_record = maps[f"{site}-{name}"]
            offer = map_record["offer"]
            prediction, = [p for p in predictions if p["region"] == offer
                           and p["recording"] == RECORDINGS[site]]
            identity = original_release_binding(
                site, offer, prediction, map_record["native_sha256"]
            )
            fits.append(replay(
                site, name, offer, map_record["points"], prediction["arms"], identity,
                map_record["cpu_s"]["probes"],
            ))
    write(output, {"results": fits, "input_sha256": {
        "india": INDIA_PIN, "mirrors": MIRRORS_PIN,
        "released_maps": ARCHIVE_PIN, "predictions": PREDICTIONS_PIN,
    }})


def score(pinned, output):
    from tools.pipeline_eval.qualification.score_paired_holdout import face_clearance_km
    from tools.pipeline_eval.scoring import distance_km

    data = read(pinned)
    truth = references()
    for row in data["results"]:
        point = truth[row["site"]]
        clearance = face_clearance_km(row["offer"], point)
        row["truth_clearance_km"] = clearance
        row["geographic_decision_correct"] = row["would_withhold"] == (clearance < 0)
        for arm in row["arms"].values():
            arm["horizontal_error_km"] = distance_km(arm["latlon"], point)
    data["inference_sha256"] = file_sha(pinned)
    write(output, data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    tasks = parser.add_subparsers(dest="task", required=True)
    work = tasks.add_parser("run")
    work.add_argument("output", type=Path)
    scored = tasks.add_parser("score")
    scored.add_argument("pinned", type=Path)
    scored.add_argument("output", type=Path)
    args = vars(parser.parse_args())
    (run if args.pop("task") == "run" else score)(**args)


if __name__ == "__main__":
    main()
