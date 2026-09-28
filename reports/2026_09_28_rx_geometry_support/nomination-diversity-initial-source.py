#!/usr/bin/env python3
"""Audit calibration nomination diversity after grouping duplicate catalogues."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path


def logsumexp(values: list[float]) -> float:
    maximum = max(values)
    return maximum + math.log(math.fsum(math.exp(value - maximum) for value in values))


def weighted_quantile(rows: list[tuple[float, float]], probability: float) -> float | None:
    if not rows:
        return None
    ordered = sorted(rows)
    threshold = probability * math.fsum(weight for _, weight in ordered)
    cumulative = 0.0
    for value, weight in ordered:
        cumulative += weight
        if cumulative >= threshold:
            return value
    return ordered[-1][0]


def audit(document: dict) -> dict:
    if document.get("schema") != "rx-geometry-dataset/v1":
        raise ValueError("unsupported dataset schema")
    lanes = []
    seen_windows: set[str] = set()
    for lane in document["lanes"]:
        if lane["recording_split"] != "calibration":
            continue
        components = lane["components"]
        if not components or components[-1].get("kind") != "other":
            raise ValueError("lane must end in the other component")
        nominees = components[:-1]
        if not nominees or any(row.get("kind") != "track_candidate" for row in nominees):
            raise ValueError("lane nominees must be track candidates")
        reception = [window for window in lane["windows"] if window["role"] == "reception"]
        if not reception:
            raise ValueError("calibration lane lacks reception windows")
        for window in reception:
            window_id = window["source_window_id"]
            if window_id in seen_windows:
                raise ValueError("duplicate calibration reception window")
            seen_windows.add(window_id)
            if len(window["predictions"]) != len(nominees):
                raise ValueError("prediction/component cardinality mismatch")

        finite = [float(row["log_prior"]) for row in nominees if row["log_prior"] is not None]
        normalizer = logsumexp(finite)
        by_catalog: dict[int, list[int]] = defaultdict(list)
        for index, row in enumerate(nominees):
            if row["log_prior"] is not None:
                by_catalog[int(row["catalog_number"])].append(index)
        catalog_rows = []
        for catalog, indices in sorted(by_catalog.items()):
            log_mass = logsumexp([float(nominees[index]["log_prior"]) for index in indices])
            mass = math.exp(log_mass - normalizer)
            endpoint_vectors = []
            for window in (reception[0], reception[-1]):
                vector = [0.0, 0.0, 0.0]
                within = [
                    math.exp(float(nominees[index]["log_prior"]) - log_mass) for index in indices
                ]
                for weight, index in zip(within, indices, strict=True):
                    los = window["predictions"][index]["los_enu_unit"]
                    for axis, key in enumerate(("east", "north", "up")):
                        vector[axis] += weight * float(los[key])
                endpoint_vectors.append(vector)
            delta = [right - left for left, right in zip(*endpoint_vectors, strict=True)]
            catalog_rows.append(
                {
                    "catalog_number": catalog,
                    "track_hypotheses": len(indices),
                    "mass": mass,
                    "endpoint_delta_los_enu": delta,
                }
            )

        masses = [row["mass"] for row in catalog_rows]
        entropy = -math.fsum(mass * math.log(mass) for mass in masses if mass > 0)
        pairs = []
        for left_index, left in enumerate(catalog_rows):
            for right in catalog_rows[left_index + 1 :]:
                a, b = left["endpoint_delta_los_enu"], right["endpoint_delta_los_enu"]
                norm_a = math.sqrt(math.fsum(value * value for value in a))
                norm_b = math.sqrt(math.fsum(value * value for value in b))
                if norm_a == 0 or norm_b == 0:
                    continue
                cosine = math.fsum(x * y for x, y in zip(a, b, strict=True)) / (norm_a * norm_b)
                angle = math.degrees(math.acos(max(-1.0, min(1.0, cosine))))
                pairs.append((angle, left["mass"] * right["mass"]))
        pair_weight = math.fsum(weight for _, weight in pairs)
        direction = {
            "distinct_catalog_pairs": len(pairs),
            "prior_pair_mass": pair_weight,
            "weighted_mean_angle_deg": None
            if pair_weight == 0
            else math.fsum(angle * weight for angle, weight in pairs) / pair_weight,
            "weighted_median_angle_deg": weighted_quantile(pairs, 0.5),
            "minimum_angle_deg": None if not pairs else min(angle for angle, _ in pairs),
            "maximum_angle_deg": None if not pairs else max(angle for angle, _ in pairs),
        }
        lanes.append(
            {
                "lane": lane["lane"],
                "reception_windows": len(reception),
                "track_hypotheses": len(finite),
                "catalogue_summary": {
                    "distinct_catalogues": len(catalog_rows),
                    "entropy_nats": entropy,
                    "effective_count": math.exp(entropy),
                    "maximum_mass": max(masses),
                    "mass_ge_1e_6_count": sum(mass >= 1e-6 for mass in masses),
                },
                "catalogues": catalog_rows,
                "endpoint_delta_direction_disagreement": direction,
            }
        )
    if len(lanes) != 12:
        raise ValueError("expected twelve calibration lanes")
    return {
        "schema": "rx-geometry-nomination-diversity/v1",
        "scope": "calibration reception only; grouped by catalogue number",
        "lanes": lanes,
        "summary": {
            "lanes": len(lanes),
            "one_material_catalogue_lanes": sum(
                row["catalogue_summary"]["mass_ge_1e_6_count"] == 1 for row in lanes
            ),
            "multiple_material_catalogue_lanes": sum(
                row["catalogue_summary"]["mass_ge_1e_6_count"] > 1 for row in lanes
            ),
        },
        "interpretation": (
            "Catalogue alternatives are conditional training-prior hypotheses, not decoded truth. "
            "Direction disagreement compares first-to-last LOS delta vectors between distinct "
            "catalogues and does not establish identity."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    payload = args.dataset.read_bytes()
    result = audit(json.loads(payload))
    result["dataset_sha256"] = hashlib.sha256(payload).hexdigest()
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
