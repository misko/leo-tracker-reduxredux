#!/usr/bin/env python3
"""Audit a defensible no-nominated-visible reception background population."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from statistics import fmean, pvariance
from typing import Any

BINS = 16


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _moments(values: list[int]) -> dict[str, float | int | None]:
    return {
        "n": len(values),
        "mean": fmean(values) if values else None,
        "population_variance": pvariance(values) if values else None,
        "minimum": min(values) if values else None,
        "maximum": max(values) if values else None,
    }


def build_audit(
    documents: list[tuple[str, dict[str, Any]]], *, population: str = "all_invisible"
) -> dict[str, Any]:
    if population not in {"all_invisible", "unconditional"}:
        raise ValueError("unsupported background population")
    lane_counts: list[int] = []
    receiver_counts = {"rx0": [], "rx1": []}
    empty = Counter()
    bins = [0] * BINS
    source_counts = Counter()
    source_reception_counts = Counter()
    lanes = []
    seen_windows = set()
    for source, document in documents:
        if document.get("schema") != "rx-geometry-dataset/v1":
            raise ValueError(f"unsupported dataset schema: {source}")
        source_counts[source] += 0
        source_reception_counts[source] += 0
        for lane in document.get("lanes", []):
            if lane.get("recording_split") != "calibration":
                continue
            period = float(lane["alias_period_hz"])
            if not math.isfinite(period) or period <= 0:
                raise ValueError("lane alias period must be finite and positive")
            lane_negative = 0
            lane_reception = 0
            lane_candidates = 0
            for window in lane.get("windows", []):
                if window.get("role") != "reception":
                    continue
                lane_reception += 1
                source_reception_counts[source] += 1
                predictions = window.get("predictions")
                if not isinstance(predictions, list) or not predictions:
                    raise ValueError("reception window lacks nominated predictions")
                if any(not isinstance(row.get("visible"), bool) for row in predictions):
                    raise ValueError("prediction visibility must be boolean")
                if population == "all_invisible" and any(row["visible"] for row in predictions):
                    continue
                window_id = window.get("source_window_id")
                if not isinstance(window_id, str) or window_id in seen_windows:
                    raise ValueError("negative window identity is missing or duplicated")
                seen_windows.add(window_id)
                observed = window.get("observed", {})
                if set(observed) != {"rx0", "rx1"}:
                    raise ValueError("negative window lacks paired receiver observations")
                counts = {receiver: len(observed[receiver]) for receiver in ("rx0", "rx1")}
                for receiver, count in counts.items():
                    receiver_counts[receiver].append(count)
                    empty[receiver] += count == 0
                    for candidate in observed[receiver]:
                        frequency = float(candidate["canonical_rx0_hz"])
                        if not math.isfinite(frequency):
                            raise ValueError("observed canonical frequency is not finite")
                        index = min(BINS - 1, int((frequency % period) / period * BINS))
                        bins[index] += 1
                if counts["rx0"] == 0 and counts["rx1"] == 0:
                    empty["both"] += 1
                if counts["rx0"] == 0 or counts["rx1"] == 0:
                    empty["either"] += 1
                lane_negative += 1
                lane_candidates += counts["rx0"] + counts["rx1"]
                source_counts[source] += 1
            lane_counts.append(lane_negative)
            lanes.append(
                {
                    "source": source,
                    "lane": lane["lane"],
                    "negative_windows": lane_negative,
                    "calibration_reception_windows": lane_reception,
                    "raw_candidates": lane_candidates,
                }
            )
    windows = len(seen_windows)
    receiver_moments = {receiver: _moments(values) for receiver, values in receiver_counts.items()}
    poisson_diagnostics = {}
    for receiver, moments in receiver_moments.items():
        mean = moments["mean"]
        variance = moments["population_variance"]
        observed_empty = empty[receiver] / windows if windows else None
        poisson_empty = math.exp(-mean) if isinstance(mean, float) else None
        poisson_diagnostics[receiver] = {
            "variance_to_mean": variance / mean if mean else None,
            "observed_empty_fraction": observed_empty,
            "poisson_empty_fraction_at_observed_mean": poisson_empty,
            "empty_fraction_difference": (
                observed_empty - poisson_empty
                if observed_empty is not None and poisson_empty is not None
                else None
            ),
        }
    total_candidates = sum(bins)
    expected = total_candidates / BINS if total_candidates else 0.0
    chi_square = sum((count - expected) ** 2 / expected for count in bins) if expected else None
    return {
        "schema": "rx-background-audit/v1",
        "population": population,
        "population_definition": (
            "recording_split=calibration and role=reception; mixed observational reference"
            if population == "unconditional"
            else "recording_split=calibration, role=reception, and every nominated "
            "track-candidate prediction has visible=false"
        ),
        "population_windows": windows,
        "negative_windows": windows if population == "all_invisible" else None,
        "calibration_reception_windows": sum(source_reception_counts.values()),
        "negative_window_fraction": (
            windows / sum(source_reception_counts.values()) if source_reception_counts else None
        ),
        "source_calibration_reception_windows": dict(sorted(source_reception_counts.items())),
        "source_population_windows": dict(sorted(source_counts.items())),
        "source_negative_windows": (
            dict(sorted(source_counts.items())) if population == "all_invisible" else None
        ),
        "receiver_candidate_counts": receiver_moments,
        "poisson_count_diagnostics": poisson_diagnostics,
        "empty_fractions": {
            "rx0": empty["rx0"] / windows if windows else None,
            "rx1": empty["rx1"] / windows if windows else None,
            "either_receiver": empty["either"] / windows if windows else None,
            "both_receivers": empty["both"] / windows if windows else None,
        },
        "lane_population_window_dispersion": _moments(lane_counts),
        "lane_negative_window_dispersion": (
            _moments(lane_counts) if population == "all_invisible" else None
        ),
        "lanes": lanes,
        "frequency_circle": {
            "bins": BINS,
            "interval": "[k/16,(k+1)/16) of canonical_rx0_hz modulo lane alias_period_hz",
            "candidate_count": total_candidates,
            "counts": bins,
            "fractions": [count / total_candidates if total_candidates else None for count in bins],
            "pearson_chi_square_vs_equal_bins": chi_square,
        },
        "interpretation": (
            "Unconditional calibration reception is a mixed observational reference, not "
            "labelled clutter truth; this audit estimates no parameters."
            if population == "unconditional"
            else "No-nominated-visible is a model-defined reference population, not labelled "
            "clutter truth; this audit estimates no parameters."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, action="append", required=True)
    parser.add_argument(
        "--population", choices=("all_invisible", "unconditional"), default="all_invisible"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    documents = [(str(path), json.loads(path.read_text())) for path in args.dataset]
    result = build_audit(documents, population=args.population)
    result["source_digests"] = {str(path): digest(path) for path in args.dataset}
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
