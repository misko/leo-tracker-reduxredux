"""Freeze phase-blind dual-RX candidate bindings for one adaptive 300 s session.

This reads only published analysis metadata.  It deliberately does not open an
IQ visit: replay code may use its output later, without reselecting candidates
after seeing a phase result.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from leo.application.adaptive_dual_rx_phase_v2 import _phase_blind_pairs
from leo.scanner.host_adaptive_products import bind_actual_visit_analysis
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore

SESSION_ID = "scan-hop-28d7592ea614f624"
OUTPUT = Path("reports/figures/2026_09_23_adaptive_phase_300s/binding.json")
PROBE_STRIDE_MS = 120


def _candidate(candidate: object) -> dict[str, float | int | str]:
    """Keep every persisted field needed to reconstruct a source template."""
    return {
        "candidate_rank": candidate.candidate_rank,
        "integer_epoch_sample": candidate.integer_epoch_sample,
        "integer_device_sample_counter": candidate.integer_device_sample_counter,
        "integer_session_sample": candidate.integer_session_sample,
        "fractional_epoch_offset_samples": candidate.fractional_epoch_offset_samples,
        "fractional_time_s": candidate.fractional_time_s,
        "acquired_cfo_hz": candidate.acquired_cfo_hz,
        "integer_tracking_cfo_hz": candidate.integer_tracking_cfo_hz,
        "fractional_tracking_cfo_hz": candidate.fractional_tracking_cfo_hz,
        "fractional_margin": candidate.fractional_margin,
    }


def _pair_record(left: object, right: object, receiver_offset_hz: float, start: int) -> dict:
    source = {
        "epoch": left.integer_epoch_sample,
        "fractional_epoch": left.fractional_epoch_offset_samples,
        "rx0_acquired_cfo_hz": left.acquired_cfo_hz,
        "rx1_original_acquired_cfo_hz": right.acquired_cfo_hz,
        "quality": min(left.fractional_margin, right.fractional_margin),
    }
    return {
        "probe_start_samples": start,
        "receiver_offset_hz": receiver_offset_hz,
        "quality": source["quality"],
        "source": source,
        "rx0": _candidate(left),
        "rx1": _candidate(right),
    }


def _primary_key(pair: dict) -> tuple[float, int, int, int]:
    """A phase-blind stable choice among already one-to-one matched pairs."""
    return (
        -pair["quality"],
        pair["probe_start_samples"],
        pair["rx0"]["candidate_rank"],
        pair["rx1"]["candidate_rank"],
    )


def run(output: Path = OUTPUT) -> dict:
    root = Path("/srv/bulk/leo")
    captures = AdaptiveHopIqStore(root, read_only=True)
    analyses = AdaptiveHopAnalysisStore(root, read_only=True)
    try:
        publication = captures.inspect(SESSION_ID)
        receipt = publication.manifest.receipt
        sample_rate_hz = receipt.plan.geometry.sample_rate_hz
        binding = bind_actual_visit_analysis(
            receipt,
            input_manifest_sha256=publication.manifest_sha256,
            probe_stride_ms=PROBE_STRIDE_MS,
        )
        channel_summary: dict[str, dict] = defaultdict(
            lambda: {
                "published_visit_count": 0,
                "visit_with_pair_count": 0,
                "pair_record_count": 0,
                "multi_pair_visit_count": 0,
            }
        )
        rows = []
        with analyses.job(binding) as job:
            manifest = job.manifest()
            if manifest is None:
                raise RuntimeError("published analysis manifest is unavailable")
            for visit in job.published_visits():
                target = visit.target.model_dump(mode="json")
                channel_key = f"ch{target['channel']}{target['edge'][0].upper()}"
                summary = channel_summary[channel_key]
                summary["published_visit_count"] += 1
                pairs = [
                    _pair_record(left, right, offset, start)
                    for left, right, offset, start in _phase_blind_pairs(visit)
                ]
                if not pairs:
                    continue
                pairs.sort(key=_primary_key)
                summary["visit_with_pair_count"] += 1
                summary["pair_record_count"] += len(pairs)
                summary["multi_pair_visit_count"] += len(pairs) >= 2
                rows.append(
                    {
                        "visit_index": visit.visit_index,
                        "iq_ordinal": visit.visit_index,
                        "sample_rate_hz": sample_rate_hz,
                        "channel": target["channel"],
                        "edge": target["edge"],
                        "time_s": (visit.valid_start_counter - visit.source_origin_counter)
                        / sample_rate_hz,
                        "session_time_s": (visit.valid_start_counter - visit.source_origin_counter)
                        / sample_rate_hz,
                        "valid_start_counter": visit.valid_start_counter,
                        "source_origin_counter": visit.source_origin_counter,
                        "target": target,
                        "sources": [pairs[0]["source"]],
                        "primary_pair": pairs[0],
                        "phase_blind_pairs": pairs,
                    }
                )
        result = {
            "schema_version": 1,
            "kind": "adaptive_phase_300s_phase_blind_metadata_binding",
            "selection_uses_phase": False,
            "iq_opened": False,
            "session_id": SESSION_ID,
            "input_manifest_sha256": publication.manifest_sha256,
            "analysis_binding_sha256": binding.sha256,
            "probe_stride_ms": PROBE_STRIDE_MS,
            "sample_rate_hz": sample_rate_hz,
            "primary_pair_rule": (
                "highest minimum fractional margin, then probe start, RX0 rank, RX1 rank; "
                "all phase-blind one-to-one pairs retained"
            ),
            "time_reference": "(valid_start_counter - source_origin_counter) / sample_rate_hz",
            "channel_summary": dict(sorted(channel_summary.items())),
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
    print(json.dumps({"rows": len(result["rows"]), "channels": result["channel_summary"]}))
