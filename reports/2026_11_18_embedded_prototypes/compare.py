"""Score independently submitted endpoints. No prototype imports this module for inference."""

from collections import Counter
import csv
import hashlib
import json
import math
from statistics import mean, median

from bench import CASES, ROOT
from paired_controls import compare_endpoints


METHODS = (
    "01_stream", "02_pilots", "03_consensus", "04_compact", "05_stationary",
    "06_coreset", "07_differences", "08_grid", "09_events", "10_network",
)
ARMS = ("c0", "fitted_c")
REFERENCE = ROOT / "scoring-reference.json"


def read(path):
    return json.loads(path.read_bytes())


def distance_km(point, reference):
    latitude, longitude = map(math.radians, point)
    other_lat, other_lon = map(math.radians, reference)
    a = (math.sin((latitude - other_lat) / 2) ** 2
         + math.cos(latitude) * math.cos(other_lat) * math.sin((longitude - other_lon) / 2) ** 2)
    return 12742.0176 * math.asin(math.sqrt(min(1., a)))


def finite_number(value):
    return type(value) in (int, float) and math.isfinite(value)


def validate_rows(rows, expected):
    if Counter(r["case"] for r in rows) != Counter(expected):
        raise ValueError("Every sampled recording must have exactly one outcome")
    for row in rows:
        if not finite_number(row["wall_s"]) or row["wall_s"] < 0:
            raise ValueError(f"Invalid time for {row['case']}")
        if set(row["arms"]) != set(ARMS):
            raise ValueError(f"Expected both calibration arms for {row['case']}")
        for arm, value in row["arms"].items():
            status = value.get("status")
            if not isinstance(status, str) or not status.strip():
                raise ValueError(f"Missing status for {row['case']} {arm}")
            if status != "estimate":
                if value.get("latlon") is not None:
                    raise ValueError(f"Endpoint attached to {status} for {row['case']} {arm}")
                continue
            ll = value.get("latlon")
            if (not isinstance(ll, (tuple, list)) or len(ll) != 2 or not all(map(finite_number, ll))
                    or abs(ll[0]) > 90 or abs(ll[1]) > 180):
                raise ValueError(f"Invalid coordinates for {row['case']} {arm}")
            rms = value["rms_hz"]
            if rms is not None and (not finite_number(rms) or rms < 0):
                raise ValueError(f"Invalid frequency residual for {row['case']} {arm}")


def scored_rows(method, document, expected, reference):
    validate_rows(document["cases"], expected)
    scored = []
    for row in document["cases"]:
        for arm in ARMS:
            value = row["arms"][arm]
            ll = value.get("latlon") if value["status"] == "estimate" else None
            scored.append(dict(method=method, case=row["case"], arm=arm, status=value["status"],
                               latitude_deg=ll[0] if ll else None, longitude_deg=ll[1] if ll else None,
                               error_km=distance_km(ll, reference) if ll else None,
                               rms_hz=value.get("rms_hz"), wall_s=row["wall_s"]))
    return scored


def summarize(scored, reference_errors):
    result = {}
    for arm in ARMS:
        by_arm = [r for r in scored if r["arm"] == arm]
        estimated = [r for r in by_arm if r["status"] == "estimate"]
        paired = [r for r in estimated if (r["case"], arm) in reference_errors]
        errors = [r["error_km"] for r in estimated]
        residuals = [r["rms_hz"] for r in estimated if r["rms_hz"] is not None]
        deltas = [r["error_km"] - reference_errors[r["case"], arm] for r in paired]
        worst = max(estimated, key=lambda r: r["error_km"], default=None)
        result[arm] = dict(n_cases=len(by_arm), n_estimates=len(estimated),
                           statuses=dict(Counter(r["status"] for r in by_arm)),
                           median_error_km=median(errors) if errors else None,
                           mean_error_km=mean(errors) if errors else None,
                           worst_error_km=worst["error_km"] if worst else None,
                           worst_case=worst["case"] if worst else None,
                           median_selected_rms_hz=median(residuals) if residuals else None,
                           paired_v5_n=len(deltas),
                           paired_v5_mean_delta_km=mean(deltas) if deltas else None,
                           closer_than_v5=sum(d < 0 for d in deltas))
    return result


def write_csv(name, rows):
    with (ROOT / name).open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def score_streaming_combination(reference, v5, streaming_rows):
    report = read(ROOT / "stream_coreset_check" / "result.json")
    combined = scored_rows("stream_coreset_check", report, CASES, reference)
    controls = [{"case": row["case"], "wall_s": row["full_control"]["logical_total_wall_s"],
                 "arms": row["full_control"]["arms"]} for row in report["cases"]]
    full = scored_rows("same_stream_full", {"cases": controls}, CASES, reference)
    original = {(r["case"], r["arm"]): r for r in streaming_rows}
    for result in full:
        other = original[result["case"], result["arm"]]
        if result["status"] != other["status"]:
            raise ValueError("Integration control changed streaming coverage")
        if result["status"] == "estimate" and distance_km(
                (result["latitude_deg"], result["longitude_deg"]),
                (other["latitude_deg"], other["longitude_deg"])) > 1.e-6:
            raise ValueError("Integration control did not reproduce the streaming primary")
    write_csv("stream-coreset-scores.csv", combined + full)
    return dict(arms=summarize(combined, v5), timing_scope=report["timing_scope"],
                median_wall_s=median(r["wall_s"] for r in report["cases"]))


def main():
    site = read(REFERENCE)
    reference = site["latitude_deg"], site["longitude_deg"]
    controls = read(ROOT / "controls.json")
    docs = {key: dict(cases=rows, timing_scope=controls["timing_scope"][key])
            for key, rows in controls["controls"].items()}
    for method in METHODS:
        docs[method] = read(ROOT / method / "result.json")
        if not docs[method]["timing_scope"] or not docs[method]["checks"]:
            raise ValueError(f"Source needs timing scope and checks for {method}")
    rows = {key: scored_rows(key, document, CASES, reference) for key, document in docs.items()}
    v5 = {(r["case"], r["arm"]): r["error_km"] for r in rows["v5_r0"] if r["error_km"] is not None}
    results = {}
    for key, points in rows.items():
        results[key] = dict(arms=summarize(points, v5), timing_scope=docs[key]["timing_scope"],
                            median_wall_s=median(r["wall_s"] for r in docs[key]["cases"]))
    all_rows = [row for points in rows.values() for row in points]
    write_csv("scores.csv", all_rows)
    comparisons = [r for method in METHODS for r in compare_endpoints(
        method, docs[method], reference, distance_km)]
    write_csv("paired-controls.csv", comparisons)
    hashes = {key: hashlib.sha256((ROOT / key / "result.json").read_bytes()).hexdigest() for key in METHODS}
    evidence = ("panel.json", "scoring-reference.json", "controls.json", "02_pilots/iq-check.json",
                "02_pilots/scout-policy-control.json", "stream_coreset_check/result.json", "10_network/weights.npy")
    evidence_hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in evidence}
    supplementary = score_streaming_combination(reference, v5, rows["01_stream"])
    output = dict(panel=CASES, reference=site, result_sha256=hashes, evidence_sha256=evidence_hashes, methods=results,
                  stream_coreset_compatibility=supplementary)
    (ROOT / "comparison.json").write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
