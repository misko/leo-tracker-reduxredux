"""Freeze an RX0-anchored, phase-blind adaptive replay cohort.

The relaxed cohort deliberately requires only one passed candidate in each
receiver.  Every retained source template is an alias-aware 5 kHz-distinct RX0
candidate; RX1 is measured at the shared RX0 epoch with a receiver offset to
be estimated from training IQ later.  It is therefore a coherence cohort, not
a claim that every RX0 anchor was independently detected at RX1.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from leo.analysis.starlink.adaptive_dual_rx_phase import circular_frequency_delta
from leo.application.adaptive_dual_rx_phase_v2 import _phase_blind_pairs, _timing_residual_samples
from leo.scanner.host_adaptive_products import bind_actual_visit_analysis
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore

SESSION_ID = "scan-hop-28d7592ea614f624"
OUT = Path("reports/figures/2026_09_23_scan_glrt_multiplicity/relaxed-rx0-anchor-binding.json")
DISTINCT_HZ = 5_000.0


def _candidate(candidate: object) -> dict:
    return {
        "rank": candidate.candidate_rank,
        "epoch": candidate.integer_epoch_sample,
        "fractional_epoch": candidate.fractional_epoch_offset_samples,
        "acquired_cfo_hz": candidate.acquired_cfo_hz,
        "tracking_cfo_hz": candidate.fractional_tracking_cfo_hz,
        "quality": candidate.fractional_margin,
    }


def _distinct(candidates: list[object]) -> list[object]:
    retained = []
    for candidate in sorted(
        candidates,
        key=lambda item: (
            -item.fractional_margin,
            item.candidate_rank,
            item.fractional_tracking_cfo_hz,
        ),
    ):
        if all(
            abs(
                circular_frequency_delta(
                    candidate.fractional_tracking_cfo_hz, old.fractional_tracking_cfo_hz
                )
            )
            >= DISTINCT_HZ
            for old in retained
        ):
            retained.append(candidate)
    return retained


def run(output: Path = OUT, *, anchor_receiver: int = 0) -> dict:
    if anchor_receiver not in (0, 1):
        raise ValueError("anchor_receiver must be 0 or 1")
    opposite_receiver = 1 - anchor_receiver
    root = Path("/srv/bulk/leo")
    captures = AdaptiveHopIqStore(root, read_only=True)
    analyses = AdaptiveHopAnalysisStore(root, read_only=True)
    try:
        publication = captures.inspect(SESSION_ID)
        receipt = publication.manifest.receipt
        sample_rate_hz = receipt.plan.geometry.sample_rate_hz
        binding = bind_actual_visit_analysis(
            receipt, input_manifest_sha256=publication.manifest_sha256, probe_stride_ms=120
        )
        rows = []
        channels: dict[str, Counter] = defaultdict(Counter)
        with analyses.job(binding) as job:
            if job.manifest() is None:
                raise RuntimeError("published analysis manifest unavailable")
            for visit in job.published_visits():
                rx0 = [
                    candidate
                    for probe in visit.probes
                    if probe.receiver_id == 0
                    for candidate in probe.candidates
                    if candidate.passed_fractional_margin_gate
                ]
                rx1 = [
                    candidate
                    for probe in visit.probes
                    if probe.receiver_id == 1
                    for candidate in probe.candidates
                    if candidate.passed_fractional_margin_gate
                ]
                by_receiver = {0: rx0, 1: rx1}
                if not by_receiver[anchor_receiver] or not by_receiver[opposite_receiver]:
                    continue
                anchors = _distinct(by_receiver[anchor_receiver])
                frame_period = visit.configuration.sample_rate_hz / 750.0
                source_rows = []
                for anchor in anchors:
                    nearest = min(
                        by_receiver[opposite_receiver],
                        key=lambda candidate: _timing_residual_samples(
                            anchor, candidate, frame_period
                        ),
                    )
                    timing = _timing_residual_samples(anchor, nearest, frame_period)
                    source_rows.append(
                        {
                            **_candidate(anchor),
                            "anchor_receiver": anchor_receiver,
                            "native_acquired_cfo_hz": anchor.acquired_cfo_hz,
                            "rx0_acquired_cfo_hz": anchor.acquired_cfo_hz
                            if anchor_receiver == 0
                            else None,
                            "rx1_acquired_cfo_hz": anchor.acquired_cfo_hz
                            if anchor_receiver == 1
                            else None,
                            "nearest_opposite_receiver_candidate": _candidate(nearest),
                            "nearest_opposite_receiver_timing_residual_samples": timing,
                            "nearest_opposite_receiver_tracking_offset_hz": (
                                nearest.fractional_tracking_cfo_hz
                                - anchor.fractional_tracking_cfo_hz
                            ),
                            "cross_receiver_timing_within_9_samples": timing <= 9.0,
                        }
                    )
                target = visit.target.model_dump(mode="json")
                phase_blind = _phase_blind_pairs(visit)
                key = f"ch{target['channel']}{target['edge'][0].upper()}"
                channels[key]["visits"] += 1
                channels[key][f"rx{anchor_receiver}_anchor_count"] += len(source_rows)
                channels[key][f"rx{anchor_receiver}_multi_anchor_visits"] += len(source_rows) >= 2
                channels[key]["strict_pair_visits"] += len(phase_blind) >= 1
                channels[key]["strict_reference_two_source_visits"] += len(phase_blind) >= 2
                rows.append(
                    {
                        "session_id": SESSION_ID,
                        "input_manifest_sha256": publication.manifest_sha256,
                        "visit_index": visit.visit_index,
                        "iq_ordinal": visit.visit_index,
                        "sample_rate_hz": sample_rate_hz,
                        "channel": target["channel"],
                        "edge": target["edge"],
                        "time_s": (visit.valid_start_counter - visit.source_origin_counter)
                        / sample_rate_hz,
                        "anchor_receiver": anchor_receiver,
                        "anchor_sources": source_rows,
                        # Kept as an explicit compatibility field for the first RX0 binding.
                        "rx0_anchor_sources": source_rows if anchor_receiver == 0 else None,
                        "rx1_passed_candidate_count": len(rx1),
                        "strict_phase_blind_pair_count": len(phase_blind),
                        "strict_reference_two_source": len(phase_blind) >= 2,
                    }
                )
        result = {
            "schema_version": 1,
            "kind": f"adaptive_relaxed_rx{anchor_receiver}_anchor_phase_binding",
            "iq_opened": False,
            "selection_uses_phase": False,
            "session_id": SESSION_ID,
            "input_manifest_sha256": publication.manifest_sha256,
            "analysis_binding_sha256": binding.sha256,
            "sample_rate_hz": sample_rate_hz,
            "anchor_receiver": anchor_receiver,
            "anchor_policy": (
                f"all RX{anchor_receiver} candidates passing the persisted fractional-margin gate, "
                "greedily deduplicated at 5 kHz modulo the 1/4.4 us symbol alias"
            ),
            "rx1_policy": (
                f"no RX{opposite_receiver} timing gate for inclusion; later replay uses the "
                f"RX{anchor_receiver} anchor epoch "
                "and a training-only raw receiver-offset estimate"
            ),
            "strict_reference_policy": (
                "current _phase_blind_pairs count retained only for comparison"
            ),
            "by_channel": {key: dict(value) for key, value in sorted(channels.items())},
            "rows": rows,
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2) + "\n")
        return result
    finally:
        captures.close()
        analyses.close()


if __name__ == "__main__":
    result = run()
    print(json.dumps({"rows": len(result["rows"]), "by_channel": result["by_channel"]}, indent=2))
