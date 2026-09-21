#!/usr/bin/env python3
"""Replay the bounded two-visit shared-residual phase-reference audit."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
from report_adaptive_dual_rx_raw_coherence import cross_ambiguity_peak

from leo.analysis.starlink.adaptive_dual_rx_phase import SYMBOL_ALIAS_HZ
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

VISITS = (1354, 1428)


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


def run(bulk_root: Path, session_id: str) -> dict[str, object]:
    store = AdaptiveHopIqStore(bulk_root, read_only=True)
    rows = []
    try:
        inspected = store.inspect(session_id)
        with AdaptiveHopAnalysisInputStore(store).source(session_id) as source:
            configuration = AdaptiveHopAnalysisConfigurationV1(
                sample_rate_hz=source.receipt.plan.geometry.sample_rate_hz,
                probe_stride_ms=10,
            )
            rate = configuration.sample_rate_hz
            for visit_index in VISITS:
                iq = source.read_visit(visit_index)
                authority = cross_ambiguity_peak(iq[: len(iq) // 2], rate).frequency_hz
                visit = analyze_adaptive_hop_visit(source, visit_index, configuration=configuration)
                pair = _phase_blind_pairs(visit)[0]
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
                        "wrong_symbol_authority_controls": controls,
                    }
                )
        document = {
            "schema_version": 1,
            "kind": "adaptive_dual_rx_shared_residual_half_window_research",
            "session_id": session_id,
            "input_manifest_sha256": inspected.manifest_sha256,
            "selected_visit_indexes": list(VISITS),
            "frequency_selection_uses_phase": False,
            "published_phase_v2_modified": False,
            "visits": rows,
        }
        document["evidence_sha256"] = sha256_digest(canonical_json_bytes(document))
        return document
    finally:
        store.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--json", type=Path, required=True)
    args = parser.parse_args()
    document = run(args.bulk_root, args.session_id)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
