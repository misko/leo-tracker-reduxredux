#!/usr/bin/env python3
"""Audit joint empirical-reference geometry results."""

import argparse
import hashlib
import json
import math
from pathlib import Path

ARMS = ("D", "E", "S", "T")
EVALUATIONS = (*ARMS, "T_swap", "T_reverse", *(arm + "_shift" for arm in ARMS))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def logaddexp(left, right):
    peak = max(left, right)
    return peak + math.log(math.exp(left - peak) + math.exp(right - peak))


def joint_reference(model, left, right, period):
    observed = next(
        (
            value
            for first, second, value in model["pooled_counts"]["histogram"]
            if (first, second) == (left, right)
        ),
        0,
    )
    tail = sum(
        count * math.log(mean) - (count + 1) * math.log1p(mean)
        for count, mean in zip((left, right), model["pooled_means"], strict=True)
    )
    numerator = math.log(model["pooled_counts"]["tail_weight"]) + tail
    if observed:
        numerator = logaddexp(math.log(observed), numerator)
    count_probability = numerator - math.log(
        model["pooled_counts"]["rows"] + model["pooled_counts"]["tail_weight"]
    )
    return (
        count_probability
        + math.lgamma(left + 1)
        + math.lgamma(right + 1)
        - (left + right) * math.log(period)
    )


def raw_references(dataset, model):
    records = {}
    for lane in dataset["lanes"]:
        if lane["recording_split"] != "evaluation":
            continue
        sid = lane["lane"]["session_id"]
        row = records.setdefault(sid, {"held_windows": 0, "reference_log_score": 0.0})
        for window in lane["windows"]:
            if window["role"] != "held_frequency":
                continue
            counts = [len(window["observed"][rx]) for rx in ("rx0", "rx1")]
            row["held_windows"] += 1
            row["reference_log_score"] += joint_reference(
                model, counts[0], counts[1], lane["alias_period_hz"]
            )
    return records


def audit(results, datasets, background, source_hashes):
    if results.get("schema") != "rx-joint-geometry/v1" or results.get("status") != "complete":
        raise ValueError("results are not complete joint-geometry evidence")
    if any(
        results.get("source_sha256", {}).get(key) != value for key, value in source_hashes.items()
    ):
        raise ValueError("source hashes mismatch")
    model = background["selected_model"]
    if results.get("background_mode") != "joint" or model.get("mode") != "joint":
        raise ValueError("joint reference was not used")
    fits = {}
    for arm in ARMS:
        fit = results["fits"][arm]
        candidates = fit["candidates"]
        if [row["start"] for row in candidates] != ["neutral", "nested"]:
            raise ValueError("optimizer starts differ from frozen design")
        converged = [row for row in candidates if row["success"]]
        if not converged:
            raise ValueError("arm has no converged optimizer start")
        for row in candidates:
            expected_gain = row["calibration_relative_log_evidence"] - row["map_penalty"]
            if not math.isclose(expected_gain, row["map_gain"], abs_tol=1e-9):
                raise ValueError("candidate MAP arithmetic mismatch")
        best = max(converged, key=lambda row: row["map_gain"])
        selected = fit["selected"]
        if best["map_gain"] <= 0:
            if (
                not selected["null_selected"]
                or selected["map_gain"] != 0
                or selected["occupancy"] != 0
            ):
                raise ValueError("nonpositive arm did not select exact null")
        elif selected["null_selected"] or not math.isclose(
            selected["map_gain"], best["map_gain"], abs_tol=1e-9
        ):
            raise ValueError("arm did not select best converged positive-MAP start")
        fits[arm] = {"converged_starts": len(converged), "selected": selected}
    panels = {}
    combined = {}
    for panel_name, panel in results["panels"].items():
        if set(panel["evaluations"]) != set(EVALUATIONS):
            raise ValueError("evaluation/control population differs from design")
        reference = raw_references(datasets[panel_name], model)
        denominator = None
        evaluations = {}
        for name, evaluation in panel["evaluations"].items():
            current = {sid: row["held_windows"] for sid, row in evaluation["records"].items()}
            denominator = current if denominator is None else denominator
            if current != denominator:
                raise ValueError("control denominators differ")
            exported_score, exported_count = {}, {}
            for lane in evaluation["lanes"]:
                sid = lane["lane"]["session_id"]
                exported_score[sid] = exported_score.get(sid, 0.0) + sum(
                    lane["held_relative_scores"]
                )
                exported_count[sid] = exported_count.get(sid, 0) + len(lane["held_relative_scores"])
            evaluations[name] = {}
            for sid, row in evaluation["records"].items():
                if reference[sid]["held_windows"] != row["held_windows"] or not math.isclose(
                    reference[sid]["reference_log_score"], row["reference_log_score"], abs_tol=1e-9
                ):
                    raise ValueError("raw empirical reference does not recompute")
                if exported_count[sid] != row["held_windows"] or not math.isclose(
                    exported_score[sid], row["relative_log_score"], abs_tol=1e-9
                ):
                    raise ValueError("exported held relative scores do not sum")
                if not math.isclose(
                    row["full_log_score"],
                    row["reference_log_score"] + row["relative_log_score"],
                    abs_tol=1e-9,
                ):
                    raise ValueError("full score is not reference plus relative score")
                expected = row["relative_log_score"] / row["held_windows"]
                if not math.isclose(expected, row["versus_reference_per_window"], abs_tol=1e-12):
                    raise ValueError("per-window relative score mismatch")
                evaluations[name][sid] = expected
        expected_total = 796 if panel_name == "pilot" else 778
        if len(denominator) != 4 or sum(denominator.values()) != expected_total:
            raise ValueError("panel recording/window denominator mismatch")
        contrasts = {}
        for contrast, stored in panel["contrasts"].items():
            left, right = contrast.split("-", 1)
            values = {sid: evaluations[left][sid] - evaluations[right][sid] for sid in denominator}
            mean = sum(values.values()) / len(values)
            if values != stored["records"] or not math.isclose(mean, stored["mean"], abs_tol=1e-12):
                raise ValueError("panel contrast does not recompute")
            contrasts[contrast] = {"records": values, "mean": mean}
        panels[panel_name] = {
            "held_windows": denominator,
            "total_held_windows": sum(denominator.values()),
            "reference": reference,
            "evaluations": evaluations,
            "contrasts": contrasts,
        }
    for name, stored in results["combined_equal_record"].items():
        values = {
            sid: value
            for panel in panels.values()
            for sid, value in (
                panel["evaluations"][name.removesuffix("-reference")].items()
                if name.endswith("-reference")
                else panel["contrasts"][name]["records"].items()
            )
        }
        mean = sum(values.values()) / len(values)
        positive = sum(value > 0 for value in values.values())
        if (
            values != stored["records"]
            or not math.isclose(mean, stored["mean"], abs_tol=1e-12)
            or positive != stored["positive_records"]
        ):
            raise ValueError("combined equal-record result does not recompute")
        combined[name] = {"records": values, "mean": mean, "positive_records": positive}
    return {
        "schema": "rx-joint-geometry-result-audit/v1",
        "status": "pass",
        "source_sha256": source_hashes,
        "fits": fits,
        "panels": panels,
        "combined_equal_record": combined,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("results", "pilot", "confirmation", "background", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    source_hashes = {
        name: sha256(getattr(args, name)) for name in ("pilot", "confirmation", "background")
    }
    result = audit(
        json.loads(args.results.read_text()),
        {
            "pilot": json.loads(args.pilot.read_text()),
            "confirmation": json.loads(args.confirmation.read_text()),
        },
        json.loads(args.background.read_text()),
        source_hashes,
    )
    result["results_sha256"] = sha256(args.results)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
