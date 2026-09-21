#!/usr/bin/env python3
"""Bind saved-IQ dual-RX phase to one persisted phase-blind RF track pair."""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from leo.analysis.persistent_hop_trajectory import (  # noqa: E402
    PersistentHopTrajectoryConfig,
    reconstruct_persistent_hop_trajectories,
)
from leo.analysis.starlink.adaptive_dual_rx_phase import (  # noqa: E402
    circular_frequency_delta,
)
from leo.application.scanner_trajectory import project_scanner_candidates  # noqa: E402
from leo.contracts.digests import canonical_json_bytes, sha256_digest  # noqa: E402
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore  # noqa: E402

MAXIMUM_ALIAS_AWARE_BINDING_ERROR_HZ = 1_000.0


@dataclass(frozen=True, slots=True)
class TrackPointEvidence:
    visit_index: int
    receiver_id: int
    tracking_cfo_hz: float
    support_center_utc_ns: int
    candidate_id: str


def _track_points(
    bulk_root: Path,
    session_id: str,
    track_ids: tuple[str, str],
) -> tuple[dict[int, TrackPointEvidence], dict[int, TrackPointEvidence], dict[str, Any]]:
    source = ScannerTrackingInputStore(bulk_root)
    try:
        tracking_input = source.load(session_id)
    finally:
        source.close()
    candidates = project_scanner_candidates(tracking_input)
    config = PersistentHopTrajectoryConfig()
    trajectory = reconstruct_persistent_hop_trajectories(candidates, config=config)
    candidate_by_id = {item.candidate_id: item for item in candidates}
    tracklet_by_id = {item.tracklet_id: item for item in trajectory.tracklets}
    output = []
    for receiver_id, track_id in enumerate(track_ids):
        try:
            tracklet = tracklet_by_id[track_id]
        except KeyError as error:
            raise ValueError(f"persisted track {track_id} does not reproduce") from error
        if tracklet.lane_key[2] != receiver_id:
            raise ValueError("track order does not match RX0 then RX1")
        points: dict[int, TrackPointEvidence] = {}
        for point in tracklet.points:
            candidate = candidate_by_id[point.candidate_id]
            if candidate.visit_index in points:
                raise ValueError("persisted track has multiple points in one visit")
            points[candidate.visit_index] = TrackPointEvidence(
                visit_index=candidate.visit_index,
                receiver_id=receiver_id,
                tracking_cfo_hz=candidate.measured_cfo_hz,
                support_center_utc_ns=candidate.support_center_utc_ns,
                candidate_id=candidate.candidate_id,
            )
        output.append(points)
    return (
        output[0],
        output[1],
        {
            "trajectory_config_digest": config.digest,
            "projected_candidate_count": len(candidates),
            "reconstructed_tracklet_count": len(trajectory.tracklets),
            "tracking_input_manifest_sha256": tracking_input.input_manifest_sha256,
            "tracking_analysis_manifest_sha256": tracking_input.analysis_manifest_sha256,
            "raw_recording_authority_digest": tracking_input.raw_recording_authority_digest,
        },
    )


def bind_phase_rows(
    raw_visits: list[dict[str, Any]],
    rx0_points: dict[int, TrackPointEvidence],
    rx1_points: dict[int, TrackPointEvidence],
) -> list[dict[str, Any]]:
    """Choose the alias-aware nearest pair without consuming phase."""
    output = []
    for visit in raw_visits:
        visit_index = int(visit["visit_index"])
        if visit_index not in rx0_points or visit_index not in rx1_points:
            raise ValueError(f"selected visit {visit_index} is outside shared track support")
        track0, track1 = rx0_points[visit_index], rx1_points[visit_index]
        candidates = []
        for pair_index, pair in enumerate(visit["corrected_pairs"]):
            error0 = abs(
                circular_frequency_delta(track0.tracking_cfo_hz, float(pair["rx0_tracking_cfo_hz"]))
            )
            error1 = abs(
                circular_frequency_delta(track1.tracking_cfo_hz, float(pair["rx1_tracking_cfo_hz"]))
            )
            candidates.append((error0 + error1, max(error0, error1), pair_index, pair))
        if not candidates:
            output.append(
                {
                    "visit_index": visit_index,
                    "state": "unmatched_no_phase_blind_pair",
                }
            )
            continue
        total_error, maximum_error, pair_index, pair = min(candidates)
        if maximum_error > MAXIMUM_ALIAS_AWARE_BINDING_ERROR_HZ:
            output.append(
                {
                    "visit_index": visit_index,
                    "state": "unmatched_track_frequency_binding",
                    "minimum_alias_aware_total_error_hz": total_error,
                    "minimum_alias_aware_maximum_error_hz": maximum_error,
                }
            )
            continue
        center_utc_ns = round((track0.support_center_utc_ns + track1.support_center_utc_ns) / 2)
        output.append(
            {
                "visit_index": visit_index,
                "state": "bound_instrument_inclusive_single_difference",
                "selected_pair_index": pair_index,
                "selection_uses_phase": False,
                "support_center_utc_ns": center_utc_ns,
                "receiver_support_center_difference_ns": (
                    track1.support_center_utc_ns - track0.support_center_utc_ns
                ),
                "track_candidate_ids": [track0.candidate_id, track1.candidate_id],
                "track_tracking_cfo_hz": [
                    track0.tracking_cfo_hz,
                    track1.tracking_cfo_hz,
                ],
                "phase_pair_tracking_cfo_hz": [
                    pair["rx0_tracking_cfo_hz"],
                    pair["rx1_tracking_cfo_hz"],
                ],
                "alias_aware_binding_error_hz": [
                    abs(
                        circular_frequency_delta(
                            track0.tracking_cfo_hz,
                            float(pair["rx0_tracking_cfo_hz"]),
                        )
                    ),
                    abs(
                        circular_frequency_delta(
                            track1.tracking_cfo_hz,
                            float(pair["rx1_tracking_cfo_hz"]),
                        )
                    ),
                ],
                "phase_deg": math.degrees(float(pair["phase_rad"])),
                "conditional_phase_standard_error_deg": pair["phase_standard_error_deg"],
                "resultant": pair["resultant_length"],
                "exact_to_control_power_ratio_floor": pair["exact_to_control_power_ratio_floor"],
                "contiguous_symbol_halves_phase_error_deg": pair["controls"][
                    "contiguous_symbol_halves_phase_error_deg"
                ],
                "receiver_offset_train_hz": visit["train_peak"]["frequency_hz"],
                "receiver_offset_held_hz": visit["held_peak"]["frequency_hz"],
                "receiver_offset_train_held_difference_hz": visit[
                    "train_held_frequency_difference_hz"
                ],
                "raw_phase_pair": pair,
            }
        )
    return output


def summarize_phase_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    accepted = [
        row for row in rows if row["state"] == "bound_instrument_inclusive_single_difference"
    ]
    if not accepted:
        return {"state": "unavailable_no_bound_phase_rows"}
    accepted.sort(key=lambda row: row["support_center_utc_ns"])
    reference = accepted[0]["support_center_utc_ns"]
    for row in accepted:
        row["relative_time_s"] = (row["support_center_utc_ns"] - reference) / 1e9
    phases = np.radians([row["phase_deg"] for row in accepted])
    resultant = float(abs(np.mean(np.exp(1j * phases))))
    steps = []
    for left, right in zip(accepted, accepted[1:], strict=False):
        wrapped = math.degrees(
            float(np.angle(np.exp(1j * math.radians(right["phase_deg"] - left["phase_deg"]))))
        )
        steps.append(
            {
                "from_visit_index": left["visit_index"],
                "to_visit_index": right["visit_index"],
                "time_gap_s": right["relative_time_s"] - left["relative_time_s"],
                "wrapped_phase_change_deg": wrapped,
                "conditional_standard_error_deg": math.hypot(
                    left["conditional_phase_standard_error_deg"],
                    right["conditional_phase_standard_error_deg"],
                ),
                "continuous_cycle_count_resolved": False,
            }
        )
    return {
        "state": "measured_instrument_inclusive_per_dwell_phase",
        "bound_visit_count": len(accepted),
        "unmatched_visit_count": len(rows) - len(accepted),
        "time_span_s": accepted[-1]["relative_time_s"],
        "conditional_phase_standard_error_deg": {
            "minimum": min(row["conditional_phase_standard_error_deg"] for row in accepted),
            "median": float(
                np.median([row["conditional_phase_standard_error_deg"] for row in accepted])
            ),
            "maximum": max(row["conditional_phase_standard_error_deg"] for row in accepted),
        },
        "phase_circular_resultant": resultant,
        "phase_circular_standard_deviation_deg": (
            math.degrees(math.sqrt(-2 * math.log(resultant))) if 0 < resultant <= 1 else None
        ),
        "maximum_abs_contiguous_symbol_half_disagreement_deg": max(
            abs(row["contiguous_symbol_halves_phase_error_deg"]) for row in accepted
        ),
        "median_abs_contiguous_symbol_half_disagreement_deg": float(
            np.median([abs(row["contiguous_symbol_halves_phase_error_deg"]) for row in accepted])
        ),
        "receiver_offset_train_held_difference_hz": {
            "median_abs": float(
                np.median(
                    [abs(row["receiver_offset_train_held_difference_hz"]) for row in accepted]
                )
            ),
            "maximum_abs": max(
                abs(row["receiver_offset_train_held_difference_hz"]) for row in accepted
            ),
        },
        "wrapped_adjacent_changes": steps,
        "continuous_phase_unwrap_claimed": False,
        "geometric_phase_claimed": False,
        "reason": (
            "one source leaves the per-dwell common receiver/LNB phase gauge; "
            "adjacent wrapped changes do not identify missing integer cycles"
        ),
    }


def run(
    bulk_root: Path,
    inventory_path: Path,
    raw_evidence_path: Path,
    *,
    pair_index: int,
) -> dict[str, Any]:
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    raw = json.loads(raw_evidence_path.read_text(encoding="utf-8"))
    pair = inventory["pairs"][pair_index]
    if raw["session_id"] != pair["session_id"]:
        raise ValueError("raw phase evidence and inventory session differ")
    if raw["input_manifest_sha256"] != pair["input_manifest_sha256"]:
        raise ValueError("raw phase evidence and inventory capture authority differ")
    track_ids = tuple(pair["track_ids"])
    if len(track_ids) != 2:
        raise ValueError("dual-receiver inventory pair must contain two tracks")
    rx0_points, rx1_points, reconstruction = _track_points(bulk_root, raw["session_id"], track_ids)
    if reconstruction["raw_recording_authority_digest"] != pair["raw_recording_authority_digest"]:
        raise ValueError("reconstructed raw recording authority differs")
    rows = bind_phase_rows(raw["visits"], rx0_points, rx1_points)
    summary = summarize_phase_rows(rows)
    body = {
        "schema_version": 1,
        "kind": "recent_dual_rx_single_track_instrument_inclusive_phase_research",
        "session_id": raw["session_id"],
        "input_manifest_sha256": raw["input_manifest_sha256"],
        "raw_phase_evidence_sha256": raw["evidence_sha256"],
        "inventory_sha256": sha256_digest(canonical_json_bytes(inventory)),
        "track_ids": list(track_ids),
        "channel": pair["channel"],
        "edge": pair["edge"],
        "selection_uses_phase": False,
        "catalog_identity_claimed": False,
        "same_source_across_receivers_conditional_on_phase_blind_track_association": True,
        "maximum_alias_aware_binding_error_hz": MAXIMUM_ALIAS_AWARE_BINDING_ERROR_HZ,
        "reconstruction": reconstruction,
        "rows": rows,
        "summary": summary,
    }
    body["evidence_sha256"] = sha256_digest(canonical_json_bytes(body))
    return body


def render(document: dict[str, Any], path: Path) -> None:
    rows = [
        row
        for row in document["rows"]
        if row["state"] == "bound_instrument_inclusive_single_difference"
    ]
    figure, axes = plt.subplots(2, 1, figsize=(11, 8), layout="constrained")
    axes[0].errorbar(
        [row["relative_time_s"] for row in rows],
        [row["phase_deg"] for row in rows],
        yerr=[row["conditional_phase_standard_error_deg"] for row in rows],
        fmt="o-",
        capsize=3,
    )
    axes[0].set_ylabel("RX1−RX0 phase (deg)\nwrapped 360°, instrument-inclusive")
    axes[0].set_xlabel("time from first selected support (s)")
    axes[0].grid(alpha=0.25)
    axes[1].plot(
        [row["relative_time_s"] for row in rows],
        [row["contiguous_symbol_halves_phase_error_deg"] for row in rows],
        "o-",
        label="contiguous symbol-half difference",
    )
    axes[1].axhline(0, color="black", linewidth=0.8)
    axes[1].set_ylabel("independent-half phase difference (deg)")
    axes[1].set_xlabel("time from first selected support (s)")
    axes[1].grid(alpha=0.25)
    figure.suptitle(f"{document['session_id']} phase-blind shared-track phase")
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=160)
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--raw-evidence", type=Path, required=True)
    parser.add_argument("--pair-index", type=int, default=0)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--png", type=Path, required=True)
    args = parser.parse_args()
    document = run(
        args.bulk_root,
        args.inventory,
        args.raw_evidence,
        pair_index=args.pair_index,
    )
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    render(document, args.png)
    print(json.dumps({"evidence_sha256": document["evidence_sha256"]}, sort_keys=True))


if __name__ == "__main__":
    main()
