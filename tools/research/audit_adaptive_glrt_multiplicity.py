"""Audit phase-blind candidate multiplicity using published adaptive GLRT metadata.

No IQ is opened.  The audit recreates the matching and duplicate-frequency
filters used by ``_phase_blind_pairs`` so a display of GLRT peaks is not
mistaken for an inventory of independent sources.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from leo.analysis.starlink.adaptive_dual_rx_phase import (
    circular_frequency_delta,
    select_consistent_receiver_pairs,
)
from leo.application.adaptive_dual_rx_phase_v2 import _timing_residual_samples
from leo.scanner.host_adaptive_products import bind_actual_visit_analysis
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore


SESSION_ID = "scan-hop-28d7592ea614f624"
OUT = Path("reports/figures/2026_09_23_scan_glrt_multiplicity/gate-audit.json")
TIMING_GATE_SAMPLES = 9.0
OFFSET_SPREAD_HZ = 10_000.0
DISTINCT_FREQUENCY_HZ = 5_000.0


def _bin(distance_hz: float) -> str:
    if distance_hz < 1.0:
        return "lt_1_hz"
    if distance_hz < 100.0:
        return "1_to_100_hz"
    if distance_hz < DISTINCT_FREQUENCY_HZ:
        return "100_to_5000_hz"
    return "at_least_5000_hz"


def _candidate(candidate: object) -> dict:
    return {
        "rank": candidate.candidate_rank,
        "epoch_sample": candidate.integer_epoch_sample,
        "fractional_epoch_samples": candidate.fractional_epoch_offset_samples,
        "tracking_cfo_hz": candidate.fractional_tracking_cfo_hz,
        "fractional_margin": candidate.fractional_margin,
    }


def _frequency_groups(candidates: list[object]) -> list[object]:
    """Independent per-RX version of the same 5 kHz alias-aware uniqueness rule."""
    retained = []
    for candidate in sorted(
        candidates,
        key=lambda item: (-item.fractional_margin, item.candidate_rank, item.fractional_tracking_cfo_hz),
    ):
        if all(
            abs(circular_frequency_delta(candidate.fractional_tracking_cfo_hz, old.fractional_tracking_cfo_hz))
            >= DISTINCT_FREQUENCY_HZ
            for old in retained
        ):
            retained.append(candidate)
    return retained


def _selected_matches(visit: object) -> list[dict]:
    """Recreate the pre-distinctness one-to-one matching stage."""
    probes = {(probe.probe_index, probe.receiver_id): probe for probe in visit.probes}
    frame_period = visit.configuration.sample_rate_hz / 750.0
    selected = []
    for probe_index in sorted({key[0] for key in probes if (key[0], 0) in probes and (key[0], 1) in probes}):
        left = [x for x in probes[probe_index, 0].candidates if x.passed_fractional_margin_gate]
        right = [x for x in probes[probe_index, 1].candidates if x.passed_fractional_margin_gate]
        edges = []
        for left_index, left_candidate in enumerate(left):
            for right_index, right_candidate in enumerate(right):
                timing = _timing_residual_samples(left_candidate, right_candidate, frame_period)
                if timing <= TIMING_GATE_SAMPLES:
                    edges.append(
                        {
                            "left_index": left_index,
                            "right_index": right_index,
                            "receiver_offset_hz": right_candidate.fractional_tracking_cfo_hz
                            - left_candidate.fractional_tracking_cfo_hz,
                            "quality": min(left_candidate.fractional_margin, right_candidate.fractional_margin),
                            "timing_residual_samples": timing,
                            "probe_index": probe_index,
                            "rx0": left_candidate,
                            "rx1": right_candidate,
                        }
                    )
        matched = select_consistent_receiver_pairs(
            [(e["left_index"], e["right_index"], e["receiver_offset_hz"], e["quality"]) for e in edges],
            maximum_spread_hz=OFFSET_SPREAD_HZ,
        )
        for left_index, right_index, offset, quality in matched:
            selected.append(
                next(
                    e
                    for e in edges
                    if (e["left_index"], e["right_index"], e["receiver_offset_hz"], e["quality"])
                    == (left_index, right_index, offset, quality)
                )
            )
    return sorted(
        selected,
        key=lambda e: (-e["quality"], e["probe_index"], e["rx0"].fractional_tracking_cfo_hz),
    )


def run(output: Path = OUT) -> dict:
    root = Path("/srv/bulk/leo")
    captures = AdaptiveHopIqStore(root, read_only=True)
    analyses = AdaptiveHopAnalysisStore(root, read_only=True)
    try:
        publication = captures.inspect(SESSION_ID)
        receipt = publication.manifest.receipt
        binding = bind_actual_visit_analysis(
            receipt, input_manifest_sha256=publication.manifest_sha256, probe_stride_ms=120
        )
        summary = Counter()
        by_channel: dict[str, Counter] = defaultdict(Counter)
        rejected_rows = []
        with analyses.job(binding) as job:
            if job.manifest() is None:
                raise RuntimeError("published analysis manifest unavailable")
            for visit in job.published_visits():
                target = visit.target.model_dump(mode="json")
                channel = f"ch{target['channel']}{target['edge'][0].upper()}"
                bucket = by_channel[channel]
                summary["published_visits"] += 1
                bucket["published_visits"] += 1
                summary[f"probe_count_{len(visit.probes)}"] += 1
                bucket[f"probe_count_{len(visit.probes)}"] += 1
                candidates = {
                    receiver: [
                        candidate
                        for probe in visit.probes
                        if probe.receiver_id == receiver
                        for candidate in probe.candidates
                        if candidate.passed_fractional_margin_gate
                    ]
                    for receiver in (0, 1)
                }
                groups = {receiver: _frequency_groups(items) for receiver, items in candidates.items()}
                for counter in (summary, bucket):
                    counter["rx0_passed_ge_1"] += len(candidates[0]) >= 1
                    counter["rx1_passed_ge_1"] += len(candidates[1]) >= 1
                    counter["rx0_passed_ge_2"] += len(candidates[0]) >= 2
                    counter["rx1_passed_ge_2"] += len(candidates[1]) >= 2
                    counter["both_passed_ge_1"] += len(candidates[0]) >= 1 and len(candidates[1]) >= 1
                    counter["both_passed_ge_2"] += len(candidates[0]) >= 2 and len(candidates[1]) >= 2
                    counter["rx0_distinct_ge_2"] += len(groups[0]) >= 2
                    counter["rx1_distinct_ge_2"] += len(groups[1]) >= 2
                    counter["both_distinct_ge_2"] += len(groups[0]) >= 2 and len(groups[1]) >= 2
                matches = _selected_matches(visit)
                for counter in (summary, bucket):
                    counter["pre_distinct_pair_visits"] += len(matches) >= 1
                    counter["pre_distinct_multi_pair_visits"] += len(matches) >= 2
                    counter["pre_distinct_pairs"] += len(matches)
                retained = []
                rejected_this_visit = []
                for candidate in matches:
                    conflicts = []
                    for old in retained:
                        distance0 = abs(circular_frequency_delta(candidate["rx0"].fractional_tracking_cfo_hz, old["rx0"].fractional_tracking_cfo_hz))
                        distance1 = abs(circular_frequency_delta(candidate["rx1"].fractional_tracking_cfo_hz, old["rx1"].fractional_tracking_cfo_hz))
                        if distance0 < DISTINCT_FREQUENCY_HZ or distance1 < DISTINCT_FREQUENCY_HZ:
                            conflicts.append((distance0, distance1, old))
                    if not conflicts:
                        retained.append(candidate)
                        continue
                    distance0, distance1, old = min(conflicts, key=lambda item: min(item[0], item[1]))
                    source_separation = abs(
                        (candidate["rx0"].integer_epoch_sample + candidate["rx0"].fractional_epoch_offset_samples)
                        - (old["rx0"].integer_epoch_sample + old["rx0"].fractional_epoch_offset_samples)
                    )
                    relation = (
                        "both_receivers"
                        if distance0 < DISTINCT_FREQUENCY_HZ and distance1 < DISTINCT_FREQUENCY_HZ
                        else "rx0_only"
                        if distance0 < DISTINCT_FREQUENCY_HZ
                        else "rx1_only"
                    )
                    record = {
                        "visit_index": visit.visit_index,
                        "channel": target["channel"],
                        "receiver_collision": relation,
                        "rx0_alias_aware_distance_hz": distance0,
                        "rx1_alias_aware_distance_hz": distance1,
                        "minimum_distance_bucket": _bin(min(distance0, distance1)),
                        "rx0_distance_bucket": _bin(distance0),
                        "rx1_distance_bucket": _bin(distance1),
                        "receiver_epoch_residual_samples": candidate["timing_residual_samples"],
                        "rx0_source_epoch_separation_samples": source_separation,
                        "rejected": {"rx0": _candidate(candidate["rx0"]), "rx1": _candidate(candidate["rx1"])},
                        "retained_conflict": {"rx0": _candidate(old["rx0"]), "rx1": _candidate(old["rx1"])},
                    }
                    rejected_this_visit.append(record)
                    rejected_rows.append(record)
                    for counter in (summary, bucket):
                        counter["distinctness_rejected_pairs"] += 1
                        counter[f"collision_{relation}"] += 1
                        counter[f"minimum_distance_{record['minimum_distance_bucket']}"] += 1
                        counter[f"rx0_distance_{record['rx0_distance_bucket']}"] += 1
                        counter[f"rx1_distance_{record['rx1_distance_bucket']}"] += 1
                        counter["same_rx0_epoch_within_one_sample"] += source_separation <= 1.0
                        counter["receiver_timing_within_one_sample"] += candidate["timing_residual_samples"] <= 1.0
                for counter in (summary, bucket):
                    counter["distinctness_rejected_visits"] += bool(rejected_this_visit)
                    counter["final_distinct_pair_visits"] += len(retained) >= 1
                    counter["final_distinct_multi_pair_visits"] += len(retained) >= 2
                    counter["final_distinct_pairs"] += len(retained)
        result = {
            "schema_version": 1,
            "kind": "adaptive_glrt_multiplicity_gate_audit",
            "iq_opened": False,
            "session_id": SESSION_ID,
            "input_manifest_sha256": publication.manifest_sha256,
            "analysis_binding_sha256": binding.sha256,
            "probe_scope": "one published 20 ms probe at start 0 per 120 ms adaptive visit",
            "rules": {
                "fractional_margin": "candidate must pass persisted fractional-margin gate",
                "timing": "RX epochs agree modulo 1/750 s within 9 samples",
                "receiver_offset": "one-to-one edges share alias-aware RX1-RX0 CFO within 10 kHz",
                "distinct_source": "reject if either RX tracking CFO is within 5 kHz modulo 1/4.4 us",
            },
            "summary": dict(summary),
            "by_channel": {key: dict(value) for key, value in sorted(by_channel.items())},
            "distinctness_rejections": rejected_rows,
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2) + "\n")
        return result
    finally:
        captures.close()
        analyses.close()


if __name__ == "__main__":
    report = run()
    print(json.dumps(report["summary"], indent=2))
