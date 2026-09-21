#!/usr/bin/env python3
"""Extract and plot bounded local dual-RX phase evidence from saved adaptive IQ."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from leo.analysis.starlink.adaptive_dual_rx_phase_extract import (  # noqa: E402
    ReceiverPhaseSeed,
    extract_dual_receiver_phase,
)
from leo.contracts.digests import canonical_json_bytes, sha256_digest  # noqa: E402
from leo.scanner.adaptive_hop_products import (  # noqa: E402
    AdaptiveHopAnalysisBindingV1,
    EdgeAdaptiveAnalysisBindingV4,
)
from leo.storage.adaptive_hop import AdaptiveHopIqStore  # noqa: E402
from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore  # noqa: E402
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore  # noqa: E402


def _binding(path: Path) -> AdaptiveHopAnalysisBindingV1:
    envelope = json.loads(path.read_text())
    if set(envelope) != {"document", "sha256"} or envelope["sha256"] != sha256_digest(
        canonical_json_bytes(envelope["document"])
    ):
        raise ValueError("adaptive analysis binding seal differs")
    model = (
        EdgeAdaptiveAnalysisBindingV4
        if envelope["document"].get("schema_version") == 4
        else AdaptiveHopAnalysisBindingV1
    )
    return model.model_validate(envelope["document"])


def _phase_blind_pair(visit: Any) -> tuple[Any, Any] | None:
    probes = {probe.receiver_id: probe for probe in visit.probes if probe.probe_index == 0}
    if set(probes) != {0, 1}:
        return None
    frame_period = visit.configuration.sample_rate_hz / 750.0
    pairs = []
    for left in probes[0].candidates:
        if not left.passed_fractional_margin_gate:
            continue
        for right in probes[1].candidates:
            if not right.passed_fractional_margin_gate:
                continue
            left_epoch = left.integer_epoch_sample + left.fractional_epoch_offset_samples
            right_epoch = right.integer_epoch_sample + right.fractional_epoch_offset_samples
            difference = right_epoch - left_epoch
            timing_residual = abs(difference - round(difference / frame_period) * frame_period)
            if timing_residual <= 9.0:
                pairs.append(
                    (
                        min(left.fractional_margin, right.fractional_margin),
                        -timing_residual,
                        left,
                        right,
                    )
                )
    if not pairs:
        return None
    _, _, left, right = max(pairs, key=lambda item: (item[0], item[1]))
    return left, right


def extract(
    bulk_root: Path,
    binding_path: Path,
    *,
    maximum_visits: int,
    edge: str,
) -> dict[str, Any]:
    """Read at most ``maximum_visits`` selected saved visits and return evidence V2."""
    if not 1 <= maximum_visits <= 20:
        raise ValueError("local phase report is bounded to 1..20 visits")
    binding = _binding(binding_path)
    captures = AdaptiveHopIqStore(bulk_root, read_only=True)
    analyses = AdaptiveHopAnalysisStore(bulk_root, read_only=True)
    rows: list[dict[str, Any]] = []
    try:
        with (
            AdaptiveHopAnalysisInputStore(captures).source(binding.session_id) as source,
            analyses.job(binding) as job,
        ):
            metrics = job.manifest()
            if metrics is None:
                raise ValueError("adaptive analysis metrics are not complete")
            for visit_index in job.completed_visits():
                visit = job.read_visit(visit_index)
                if edge != "both" and visit.target.edge != edge:
                    continue
                selected = _phase_blind_pair(visit)
                if selected is None:
                    continue
                left, right = selected
                references = tuple(
                    candidate.integer_epoch_sample + candidate.fractional_epoch_offset_samples
                    for candidate in selected
                )
                observation = extract_dual_receiver_phase(
                    source.read_visit(visit_index),
                    visit.configuration.sample_rate_hz,
                    visit.target.edge,
                    left.integer_epoch_sample,
                    tuple(
                        ReceiverPhaseSeed(candidate.acquired_cfo_hz, reference)
                        for candidate, reference in zip(selected, references, strict=True)
                    ),
                )
                session_time_s = (
                    visit.valid_start_counter
                    - visit.source_origin_counter
                    + observation.center_sample
                ) / visit.configuration.sample_rate_hz
                rows.append(
                    {
                        "visit_index": visit_index,
                        "target_index": visit.target_index,
                        "edge": visit.target.edge,
                        "session_time_s": session_time_s,
                        "wrapped_rx1_minus_rx0_phase_deg": float(
                            np.degrees(observation.wrapped_phase_rad)
                        ),
                        "relative_frequency_hz": observation.relative_frequency_hz,
                        "phase_standard_error_deg": observation.phase_standard_error_deg,
                        "resultant_length": observation.resultant_length,
                        "shared_frame_count": observation.independent_frame_count,
                        "exact_to_control_power_ratio_floor": min(
                            receiver.exact_to_control_power_ratio
                            for receiver in observation.receivers
                        ),
                        "acquired_cfo_hz": [left.acquired_cfo_hz, right.acquired_cfo_hz],
                        "fractional_reference_samples": list(references),
                    }
                )
                if len(rows) >= maximum_visits:
                    break
    finally:
        analyses.close()
        captures.close()
    return {
        "schema_version": 2,
        "kind": "adaptive_dual_rx_local_phase_evidence",
        "analysis_id": "adaptive-qin-pilot-local-rx-phase-v2",
        "session_id": binding.session_id,
        "input_manifest_sha256": binding.input_manifest_sha256,
        "glrt_binding_sha256": binding.sha256,
        "glrt_metrics_manifest_sha256": sha256_digest(
            canonical_json_bytes(metrics.model_dump(mode="json"))
        ),
        "receiver_product": "rx1_times_conjugate_rx0",
        "association_uses_phase": False,
        "geometry_phase_state": "unavailable",
        "geometry_phase_reason": (
            "verified_phase_center_baseline_pose_and_chain_calibration_missing"
        ),
        "selection": {
            "maximum_visits": maximum_visits,
            "edge": edge,
            "frame_radius": 9,
            "receiver_timing_gate_samples": 9.0,
            "receiver_pair_rank": "minimum_fractional_margin_then_timing_residual",
        },
        "rows": rows,
    }


def render(document: dict[str, Any], output: Path) -> None:
    rows = document["rows"]
    if not rows:
        raise ValueError("local phase evidence contains no qualified visits")
    time_s = np.asarray([row["session_time_s"] for row in rows])
    phase_deg = np.asarray([row["wrapped_rx1_minus_rx0_phase_deg"] for row in rows])
    sigma_deg = np.asarray([row["phase_standard_error_deg"] for row in rows])
    frequency_khz = np.asarray([row["relative_frequency_hz"] for row in rows]) / 1e3
    resultants = np.asarray([row["resultant_length"] for row in rows])
    ratios = np.asarray([row["exact_to_control_power_ratio_floor"] for row in rows])
    targets = np.asarray([row["target_index"] for row in rows])
    color_min, color_max = (
        (0, 3)
        if all(row.get("edge") == "lower" for row in rows)
        else (4, 7)
        if all(row.get("edge") == "upper" for row in rows)
        else (0, 7)
    )
    figure, axes = plt.subplots(3, 1, figsize=(11, 10), sharex=True, layout="constrained")
    scatter = axes[0].scatter(
        time_s, phase_deg, c=targets, cmap="tab10", vmin=color_min, vmax=color_max
    )
    axes[0].errorbar(time_s, phase_deg, yerr=sigma_deg, fmt="none", color="0.45", alpha=0.55)
    axes[0].set_ylabel("wrapped phase (deg)")
    axes[0].set_ylim(-190, 190)
    axes[0].set_title("Local RX1−RX0 Qin-pilot phase; each visit reacquired independently")
    figure.colorbar(
        scatter,
        ax=axes[0],
        label="target index",
        ticks=range(color_min, color_max + 1),
    )
    axes[1].scatter(
        time_s,
        frequency_khz,
        c=targets,
        cmap="tab10",
        vmin=color_min,
        vmax=color_max,
    )
    axes[1].set_ylabel("RX1−RX0 frequency (kHz)")
    axes[2].plot(time_s, resultants, "o-", label="phase resultant")
    axes[2].plot(time_s, np.minimum(ratios / 10.0, 1.0), "s--", label="control ratio / 10")
    axes[2].set_ylabel("local evidence quality")
    axes[2].set_xlabel("seconds from capture origin")
    axes[2].set_ylim(0, 1.05)
    axes[2].legend(loc="best")
    for axis in axes:
        axis.grid(alpha=0.2)
    figure.suptitle(
        f"{document['session_id']} — geometry phase unavailable without calibrated baseline/pose"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=180)
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, required=True)
    parser.add_argument("--binding", type=Path, required=True)
    parser.add_argument("--maximum-visits", type=int, default=20)
    parser.add_argument("--edge", choices=("lower", "upper", "both"), default="both")
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-png", type=Path, required=True)
    args = parser.parse_args()
    document = extract(
        args.bulk_root,
        args.binding,
        maximum_visits=args.maximum_visits,
        edge=args.edge,
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(document, indent=2) + "\n")
    render(document, args.output_png)


if __name__ == "__main__":
    main()
