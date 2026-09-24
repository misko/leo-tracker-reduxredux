#!/usr/bin/env python3
"""Refine one frozen adaptive tracklet's CFOs and replay causal forecasts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

from leo.analysis.starlink.adaptive_dual_rx_phase import circular_frequency_delta
from leo.analysis.starlink.glrt_refinement_prototype import continuous_glrt_score
from leo.analysis.starlink.pilot_methods import _conditioned_correlation_workspace
from leo.application.adaptive_dual_rx_phase_v2 import _phase_blind_pairs
from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.scanner.adaptive_hop_analysis import (
    AdaptiveHopAnalysisConfigurationV1,
    analyze_adaptive_hop_visit,
)
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore


def rolling_forecasts(
    times_s: np.ndarray,
    frequencies_hz: np.ndarray,
    *,
    minimum_train_count: int = 6,
    maximum_train_count: int = 8,
) -> dict[str, dict[str, Any]]:
    """Return causal polynomial forecasts for degrees one through three."""
    times = np.asarray(times_s, dtype=float)
    values = np.asarray(frequencies_hz, dtype=float)
    if (
        times.ndim != 1
        or values.ndim != 1
        or len(times) != len(values)
        or len(times) <= minimum_train_count
        or np.any(np.diff(times) <= 0)
        or minimum_train_count < 4
        or maximum_train_count < minimum_train_count
    ):
        raise ValueError("invalid rolling frequency forecast inputs")
    output: dict[str, dict[str, Any]] = {}
    for degree in (1, 2, 3):
        predictions = []
        errors = []
        horizons = []
        for index in range(minimum_train_count, len(values)):
            begin = max(0, index - maximum_train_count)
            origin = times[index - 1]
            coefficients = np.polyfit(
                times[begin:index] - origin,
                values[begin:index],
                degree,
            )
            horizon = times[index] - origin
            prediction = float(np.polyval(coefficients, horizon))
            predictions.append(prediction)
            errors.append(prediction - values[index])
            horizons.append(float(horizon))
        error_array = np.asarray(errors)
        output[str(degree)] = {
            "degree": degree,
            "holdout_count": len(errors),
            "horizons_s": horizons,
            "predictions_hz": predictions,
            "errors_hz": errors,
            "rmse_hz": float(np.sqrt(np.mean(error_array**2))),
        }
    return output


def frequency_support_center_s(
    samples: np.ndarray,
    sample_rate_hz: int,
    *,
    anchor: int,
    offset: float,
    conditioning_cfo_hz: float,
    edge: Any,
) -> float:
    """Return the correlation-energy centroid of the GLRT64 frequency support."""
    symbols = np.arange(2, 66)
    correlations = _conditioned_correlation_workspace(
        np.asarray(samples, dtype=complex),
        sample_rate_hz,
        anchor,
        conditioning_cfo_hz,
        selected_symbols=symbols,
        fractional_epoch_offset_samples=offset,
        edge=edge,
    ).select(symbols)
    weights = np.abs(correlations.values) ** 2
    total = float(np.sum(weights))
    if not total > 0.0:
        raise ValueError("GLRT64 frequency support has zero correlation energy")
    return float(np.sum(weights * correlations.times_s) / total)


def run(bulk_root: Path, summary_path: Path) -> dict[str, Any]:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    tracks = summary.get("tracks")
    if not isinstance(tracks, list) or len(tracks) != 1:
        raise ValueError("frequency refinement requires one frozen track")
    states = tracks[0].get("states")
    if not isinstance(states, list) or not 7 <= len(states) <= 20:
        raise ValueError("frequency refinement requires seven to twenty frozen states")
    session_id = summary["session_id"]
    store = AdaptiveHopIqStore(bulk_root, read_only=True)
    rows = []
    try:
        inspected = store.inspect(session_id)
        with AdaptiveHopAnalysisInputStore(store).source(session_id) as source:
            configuration = AdaptiveHopAnalysisConfigurationV1(
                sample_rate_hz=source.receipt.plan.geometry.sample_rate_hz,
                probe_stride_ms=int(summary["probe_stride_ms"]),
            )
            for state in states:
                visit_index = int(state["visit_index"])
                iq = source.read_visit(visit_index)
                visit = analyze_adaptive_hop_visit(source, visit_index, configuration=configuration)
                pairs = _phase_blind_pairs(visit)
                row = {
                    "visit_index": visit_index,
                    "time_s": float(state["time_s"]),
                    "original_frequencies_hz": list(map(float, state["frequencies_hz"])),
                    "refined_frequencies_hz": [],
                    "source_times_s": [],
                    "signals": [],
                }
                for original_hz in row["original_frequencies_hz"]:
                    matches = (
                        (
                            abs(
                                circular_frequency_delta(
                                    original_hz, pair[0].fractional_tracking_cfo_hz
                                )
                            ),
                            pair,
                        )
                        for pair in pairs
                    )
                    match = min(matches, key=lambda item: item[0], default=None)
                    if match is None or match[0] > 1e-6:
                        raise ValueError("frozen track frequency has no source-bound candidate")
                    _, pair = match
                    candidate, _, _, probe_start = pair
                    probe = iq[
                        probe_start : probe_start + configuration.probe_samples,
                        0,
                    ]
                    score, detail = continuous_glrt_score(
                        probe,
                        configuration.sample_rate_hz,
                        anchor=candidate.integer_epoch_sample,
                        offset=candidate.fractional_epoch_offset_samples,
                        conditioning_cfo_hz=candidate.acquired_cfo_hz,
                        edge=visit.target.edge,
                    )
                    refined_hz = original_hz + circular_frequency_delta(
                        original_hz, score.tracking_cfo_hz
                    )
                    support_center_s = frequency_support_center_s(
                        probe,
                        configuration.sample_rate_hz,
                        anchor=candidate.integer_epoch_sample,
                        offset=candidate.fractional_epoch_offset_samples,
                        conditioning_cfo_hz=candidate.acquired_cfo_hz,
                        edge=visit.target.edge,
                    )
                    source_time_s = (
                        (visit.valid_start_counter - visit.source_origin_counter)
                        / configuration.sample_rate_hz
                        + probe_start / configuration.sample_rate_hz
                        + support_center_s
                    )
                    row["refined_frequencies_hz"].append(refined_hz)
                    row["source_times_s"].append(source_time_s)
                    row["signals"].append(
                        {
                            "original_tracking_cfo_hz": original_hz,
                            "refined_tracking_cfo_hz": refined_hz,
                            "refinement_hz": refined_hz - original_hz,
                            "frequency_support_session_time_s": source_time_s,
                            "double_difference_common_time_offset_s": (
                                source_time_s - row["time_s"]
                            ),
                            "exact_score": score.exact_score,
                            "control_score": score.control_score,
                            "margin": score.margin,
                            "continuous_peak": detail,
                        }
                    )
                rows.append(row)
    finally:
        store.close()
    forecasts = {}
    for source in ("original", "refined"):
        field = f"{source}_frequencies_hz"
        forecasts[source] = {
            str(signal): rolling_forecasts(
                np.asarray([row["source_times_s"][signal] for row in rows]),
                np.asarray([row[field][signal] for row in rows]),
            )
            for signal in (0, 1)
        }
    body = {
        "schema_version": 1,
        "kind": "adaptive_dual_rx_continuous_frequency_refinement_research",
        "session_id": session_id,
        "input_manifest_sha256": inspected.manifest_sha256,
        "source_summary_sha256": sha256_digest(summary_path.read_bytes()),
        "state_count": len(rows),
        "refinement": "exact_dtft_glrt64_fixed_fractional_epoch",
        "frequency_timestamp": "glrt64_correlation_energy_centroid_per_source",
        "forecast": "rolling_origin_preceding_at_most_8_first_holdout_after_6",
        "rows": rows,
        "forecasts": forecasts,
    }
    body["evidence_sha256"] = sha256_digest(canonical_json_bytes(body))
    return body


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.bulk_root, args.summary)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "states": result["state_count"],
                "evidence_sha256": result["evidence_sha256"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
