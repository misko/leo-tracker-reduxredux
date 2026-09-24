#!/usr/bin/env python3
"""Replay the bounded two-visit shared-residual phase-reference audit."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
from report_adaptive_dual_rx_raw_coherence import cross_ambiguity_peak
from report_recent_dual_rx_single_track_phase import (
    MAXIMUM_ALIAS_AWARE_BINDING_ERROR_HZ,
    _track_points,
)

from leo.analysis.starlink.adaptive_dual_rx_phase import SYMBOL_ALIAS_HZ, circular_frequency_delta
from leo.analysis.starlink.adaptive_dual_rx_phase_extract import (
    ReceiverPhaseSeed,
    extract_dual_receiver_phase_with_offset_authority,
    extract_dual_receiver_phase_with_offset_authority_shared_residual,
)
from leo.application.adaptive_dual_rx_phase_v2 import _phase_blind_pairs
from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.scanner.adaptive_hop_analysis import (
    AdaptiveHopAnalysisConfigurationV1,
    analyze_adaptive_hop_visit,
)
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore

DEFAULT_VISITS = (1354, 1428)
DEVELOPMENT_VISITS = frozenset(DEFAULT_VISITS)
TRACK_IDS = (
    "sha256:dad96c3afcf9b500c0423a9829dd442a6cf8215fd89cd4083ab0533e7b400c32",
    "sha256:d118aba06b8fdacf35a464cafbcc12e69c4affe1d6f931cd0d15cf8a016433ec",
)


def _phase_at(observation: object, sample: float, rate: float) -> float:
    return float(
        np.angle(
            np.exp(
                1j
                * (
                    observation.wrapped_phase_rad  # type: ignore[attr-defined]
                    + 2
                    * np.pi
                    * observation.relative_frequency_hz  # type: ignore[attr-defined]
                    * (sample - observation.center_sample)  # type: ignore[attr-defined]
                    / rate
                )
            )
        )
    )


def _extract(
    function: object,
    iq: np.ndarray,
    rate: float,
    visit: object,
    epoch: int,
    seeds: object,
    authority: float,
    reference: float,
    symbols: np.ndarray | None = None,
) -> object:
    return function(  # type: ignore[operator]
        iq,
        rate,
        visit.target.edge,  # type: ignore[attr-defined]
        epoch,
        seeds,
        authority,
        common_reference_sample=reference,
        symbol_indices=symbols,
    ).observation


def select_track_pair(pairs: list[object], rx0_hz: float, rx1_hz: float) -> tuple[int, object]:
    """Bind one phase-blind pair to the persisted RX0/RX1 track frequencies."""
    candidates = []
    for index, pair in enumerate(pairs):
        errors = (
            abs(circular_frequency_delta(rx0_hz, pair[0].fractional_tracking_cfo_hz)),  # type: ignore[index,union-attr]
            abs(circular_frequency_delta(rx1_hz, pair[1].fractional_tracking_cfo_hz)),  # type: ignore[index,union-attr]
        )
        candidates.append((max(errors), sum(errors), index, pair))
    if not candidates:
        raise ValueError("no phase-blind receiver pair")
    maximum, _, index, pair = min(candidates)
    if maximum > MAXIMUM_ALIAS_AWARE_BINDING_ERROR_HZ:
        raise ValueError(f"minimum track binding error {maximum:.3f} Hz exceeds gate")
    return index, pair


def summarize(rows: list[dict[str, object]]) -> dict[str, object]:
    output: dict[str, object] = {}
    all_visits = frozenset(int(row["visit_index"]) for row in rows)
    for name, selected in (
        ("development", DEVELOPMENT_VISITS & all_visits),
        ("validation", all_visits - DEVELOPMENT_VISITS),
    ):
        accepted = [
            row for row in rows if row["visit_index"] in selected and row["state"] == "evaluated"
        ]
        metrics = {}
        for key in (
            "historical_abs_half_difference_deg",
            "shared_abs_half_difference_deg",
            "abs_full_phase_shift_at_common_center_deg",
        ):
            values = np.asarray([row[key] for row in accepted], dtype=float)
            metrics[key] = (
                None
                if not len(values)
                else {
                    "minimum": float(np.min(values)),
                    "median": float(np.median(values)),
                    "maximum": float(np.max(values)),
                }
            )
        output[name] = {
            "selected_visit_count": len(selected),
            "evaluated_visit_count": len(accepted),
            "failed_visit_count": len(selected) - len(accepted),
            "metrics": metrics,
        }
    return output


def run(bulk_root: Path, session_id: str, visits: tuple[int, ...]) -> dict[str, object]:
    if not visits or len(visits) > 20 or len(set(visits)) != len(visits):
        raise ValueError("select between one and twenty unique visits")
    store = AdaptiveHopIqStore(bulk_root, read_only=True)
    rows = []
    try:
        inspected = store.inspect(session_id)
        rx0_points, rx1_points, track_reconstruction = _track_points(
            bulk_root, session_id, TRACK_IDS
        )
        with AdaptiveHopAnalysisInputStore(store).source(session_id) as source:
            configuration = AdaptiveHopAnalysisConfigurationV1(
                sample_rate_hz=source.receipt.plan.geometry.sample_rate_hz,
                probe_stride_ms=10,
            )
            rate = configuration.sample_rate_hz
            for visit_index in visits:
                try:
                    iq = source.read_visit(visit_index)
                    authority = cross_ambiguity_peak(iq[: len(iq) // 2], rate).frequency_hz
                    visit = analyze_adaptive_hop_visit(
                        source, visit_index, configuration=configuration
                    )
                    track0, track1 = rx0_points[visit_index], rx1_points[visit_index]
                    pair_index, pair = select_track_pair(
                        _phase_blind_pairs(visit),
                        track0.tracking_cfo_hz,
                        track1.tracking_cfo_hz,
                    )
                except Exception as error:  # Preserve selection and input failures per visit.
                    rows.append(
                        {
                            "visit_index": visit_index,
                            "cohort": (
                                "development" if visit_index in DEVELOPMENT_VISITS else "validation"
                            ),
                            "state": "failed_before_extraction",
                            "error_type": type(error).__name__,
                            "error": str(error),
                        }
                    )
                    continue
                left, right, _, probe_start = pair
                references = tuple(
                    probe_start + item.integer_epoch_sample + item.fractional_epoch_offset_samples
                    for item in (left, right)
                )
                seeds = (
                    ReceiverPhaseSeed(left.acquired_cfo_hz, references[0]),
                    ReceiverPhaseSeed(right.acquired_cfo_hz, references[1]),
                )
                epoch = probe_start + left.integer_epoch_sample

                arguments = (iq, rate, visit, epoch, seeds, authority, references[0])
                historical = _extract(extract_dual_receiver_phase_with_offset_authority, *arguments)
                shared = _extract(
                    extract_dual_receiver_phase_with_offset_authority_shared_residual,
                    *arguments,
                )
                methods = {}
                for name, function in (
                    ("historical", extract_dual_receiver_phase_with_offset_authority),
                    (
                        "shared_residual",
                        extract_dual_receiver_phase_with_offset_authority_shared_residual,
                    ),
                ):
                    halves = [
                        _extract(function, *arguments, symbols)
                        for symbols in (np.arange(2, 34), np.arange(34, 66))
                    ]
                    reference_sample = historical.center_sample
                    phases = [_phase_at(item, reference_sample, rate) for item in halves]
                    methods[name] = {
                        "comparison_reference_sample": reference_sample,
                        "contiguous_half_phase_difference_deg": math.degrees(
                            float(np.angle(np.exp(1j * (phases[0] - phases[1]))))
                        ),
                        "half_relative_frequency_hz": [
                            item.relative_frequency_hz for item in halves
                        ],
                        "half_receiver_residuals_hz": [
                            [receiver.within_frame_residual_cfo_hz for receiver in item.receivers]
                            for item in halves
                        ],
                        "half_resultants": [item.resultant_length for item in halves],
                        "half_center_samples": [item.center_sample for item in halves],
                    }
                controls = []
                for sign in (-1, 1):
                    wrong = extract_dual_receiver_phase_with_offset_authority_shared_residual(
                        iq,
                        rate,
                        visit.target.edge,
                        epoch,
                        seeds,
                        authority + sign * SYMBOL_ALIAS_HZ,
                        common_reference_sample=references[0],
                    ).observation
                    controls.append(
                        {
                            "authority_hz": authority + sign * SYMBOL_ALIAS_HZ,
                            "relative_frequency_hz": wrong.relative_frequency_hz,
                            "resultant": wrong.resultant_length,
                            "exact_to_control_floor": min(
                                item.exact_to_control_power_ratio for item in wrong.receivers
                            ),
                        }
                    )
                rows.append(
                    {
                        "visit_index": visit_index,
                        "cohort": (
                            "development" if visit_index in DEVELOPMENT_VISITS else "validation"
                        ),
                        "state": "evaluated",
                        "selected_pair_index": pair_index,
                        "selection_uses_phase": False,
                        "track_candidate_ids": [track0.candidate_id, track1.candidate_id],
                        "track_tracking_cfo_hz": [
                            track0.tracking_cfo_hz,
                            track1.tracking_cfo_hz,
                        ],
                        "broadband_authority_hz": authority,
                        "common_reference_sample": references[0],
                        "full_window_comparison": {
                            "comparison_reference_sample": historical.center_sample,
                            "historical_center_sample": historical.center_sample,
                            "shared_residual_center_sample": shared.center_sample,
                            "historical_phase_deg": math.degrees(historical.wrapped_phase_rad),
                            "shared_residual_phase_deg": math.degrees(shared.wrapped_phase_rad),
                            "shared_phase_at_historical_center_deg": math.degrees(
                                _phase_at(shared, historical.center_sample, rate)
                            ),
                            "wrapped_shared_minus_historical_at_common_center_deg": math.degrees(
                                float(
                                    np.angle(
                                        np.exp(
                                            1j
                                            * (
                                                _phase_at(shared, historical.center_sample, rate)
                                                - historical.wrapped_phase_rad
                                            )
                                        )
                                    )
                                )
                            ),
                            "historical_relative_frequency_hz": historical.relative_frequency_hz,
                            "shared_relative_frequency_hz": shared.relative_frequency_hz,
                            "shared_common_residual_hz": shared.receivers[
                                0
                            ].within_frame_residual_cfo_hz,
                            "historical_resultant": historical.resultant_length,
                            "shared_resultant": shared.resultant_length,
                            "historical_exact_to_control_floor": min(
                                item.exact_to_control_power_ratio for item in historical.receivers
                            ),
                            "shared_exact_to_control_floor": min(
                                item.exact_to_control_power_ratio for item in shared.receivers
                            ),
                        },
                        **methods,
                        "historical_abs_half_difference_deg": abs(
                            methods["historical"]["contiguous_half_phase_difference_deg"]
                        ),
                        "shared_abs_half_difference_deg": abs(
                            methods["shared_residual"]["contiguous_half_phase_difference_deg"]
                        ),
                        "abs_full_phase_shift_at_common_center_deg": abs(
                            math.degrees(
                                float(
                                    np.angle(
                                        np.exp(
                                            1j
                                            * (
                                                _phase_at(shared, historical.center_sample, rate)
                                                - historical.wrapped_phase_rad
                                            )
                                        )
                                    )
                                )
                            )
                        ),
                        "wrong_symbol_authority_controls": controls,
                    }
                )
        document = {
            "schema_version": 1,
            "kind": "adaptive_dual_rx_shared_residual_half_window_research",
            "session_id": session_id,
            "input_manifest_sha256": inspected.manifest_sha256,
            "selected_visit_indexes": list(visits),
            "development_visit_indexes": sorted(DEVELOPMENT_VISITS & set(visits)),
            "validation_visit_indexes": sorted(set(visits) - DEVELOPMENT_VISITS),
            "track_ids": list(TRACK_IDS),
            "track_reconstruction": track_reconstruction,
            "frequency_selection_uses_phase": False,
            "published_phase_v2_modified": False,
            "visits": rows,
            "summary": summarize(rows),
        }
        document["evidence_sha256"] = sha256_digest(canonical_json_bytes(document))
        return document
    finally:
        store.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--visits", default=",".join(map(str, DEFAULT_VISITS)))
    parser.add_argument("--json", type=Path, required=True)
    args = parser.parse_args()
    document = run(
        args.bulk_root,
        args.session_id,
        tuple(int(value) for value in args.visits.split(",") if value),
    )
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
