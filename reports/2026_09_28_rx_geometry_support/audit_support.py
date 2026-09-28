#!/usr/bin/env python3
"""Independently audit arithmetic and provenance of geometry-support results."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def close(left: float, right: float, tolerance: float = 2e-12) -> bool:
    return math.isclose(left, right, rel_tol=tolerance, abs_tol=tolerance)


def norm(vector: list[float]) -> float:
    return math.sqrt(sum(value * value for value in vector))


def audit(result: dict, dataset_hash: str, model_hash: str) -> dict:
    if result.get("schema") != "rx-geometry-support/v1":
        raise ValueError("unsupported result schema")
    if result.get("source_sha256") != {"dataset": dataset_hash, "model": model_hash}:
        raise ValueError("result input hash mismatch")
    if not close(float(result["weight_sum"]), 1.0):
        raise ValueError("global weights are not normalized")

    decomposition = result["variance_decomposition"]
    total = decomposition["total"]
    within = decomposition["within_temporal"]
    between = decomposition["between_group_means"]
    fraction = decomposition["within_fraction"]
    if not all(len(values) == 5 for values in (total, within, between, fraction)):
        raise ValueError("unexpected variance dimension")
    identity_errors = [abs(t - w - b) for t, w, b in zip(total, within, between, strict=True)]
    fraction_errors = [abs(f - w / t) for t, w, f in zip(total, within, fraction, strict=True)]
    if max(identity_errors) > 2e-12 or max(fraction_errors) > 2e-12:
        raise ValueError("variance decomposition failed")
    covariance = result["weighted_covariance"]
    symmetry_error = max(
        abs(covariance[row][column] - covariance[column][row])
        for row in range(5)
        for column in range(5)
    )
    diagonal_error = max(abs(covariance[index][index] - total[index]) for index in range(5))
    if symmetry_error > 2e-12 or diagonal_error > 2e-12:
        raise ValueError("covariance consistency failed")

    excursions = []
    spans = []
    weight_errors = []
    excursion_errors = []
    endpoint_errors = []
    unit_errors = []
    for lane in result["lanes"]:
        weights = lane["conditional_nominee_weights"]
        directions = lane["nominee_forecast_directions"]
        if len(weights) != len(directions) or not weights:
            raise ValueError("lane nominee dimensions differ")
        if any((not math.isfinite(value) or value < 0) for value in weights):
            raise ValueError("invalid nominee weight")
        weight_errors.append(abs(sum(weights) - 1.0))
        derived_excursion = sum(
            weight * row["first_last_angular_excursion_deg"]
            for weight, row in zip(weights, directions, strict=True)
        )
        excursion_errors.append(
            abs(derived_excursion - lane["weighted_nominee_los_first_last_excursion_deg"])
        )
        for weight, row in zip(weights, directions, strict=True):
            if not close(weight, row["weight"]):
                raise ValueError("direction weight mismatch")
            start = row["start_los_enu"]
            end = row["end_los_enu"]
            delta = row["endpoint_delta_los_enu"]
            calculated_delta = [right - left for left, right in zip(start, end, strict=True)]
            endpoint_errors.append(
                max(abs(a - b) for a, b in zip(delta, calculated_delta, strict=True))
            )
            endpoint_errors.append(abs(norm(delta) - row["endpoint_delta_norm"]))
            unit_errors.extend((abs(norm(start) - 1.0), abs(norm(end) - 1.0)))
        dispersions = lane["raw_feature_temporal_std"].values()
        if any(not math.isfinite(value) or value < 0 for value in dispersions):
            raise ValueError("invalid temporal feature dispersion")
        excursions.append(lane["weighted_nominee_los_first_last_excursion_deg"])
        spans.append(lane["time_span_s"])
    bounds = {
        "recordings": result["recordings"],
        "lanes": len(result["lanes"]),
        "within_temporal_fraction": [min(fraction), max(fraction)],
        "weighted_angular_excursion_deg": [min(excursions), max(excursions)],
        "reception_time_span_s": [min(spans), max(spans)],
    }
    errors = {
        "variance_identity_max_abs": max(identity_errors),
        "within_fraction_max_abs": max(fraction_errors),
        "covariance_symmetry_max_abs": symmetry_error,
        "covariance_diagonal_max_abs": diagonal_error,
        "lane_weight_sum_max_abs": max(weight_errors),
        "weighted_excursion_max_abs": max(excursion_errors),
        "endpoint_geometry_max_abs": max(endpoint_errors),
        "los_unit_norm_max_abs": max(unit_errors),
    }
    if max(errors.values()) > 2e-12:
        raise ValueError(f"geometry identity failed: {errors}")
    return {"status": "pass", "bounds": bounds, "max_absolute_errors": errors}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    result = json.loads(args.results.read_text())
    dataset_hash = digest(args.dataset)
    model_hash = digest(args.model)
    receipt = {
        "schema": "rx-geometry-support-audit/v1",
        **audit(result, dataset_hash, model_hash),
        "sha256": {
            "results": digest(args.results),
            "dataset": dataset_hash,
            "model": model_hash,
            "source": digest(args.source),
        },
    }
    with args.output.open("x") as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
