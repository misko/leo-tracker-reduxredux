"""Export the public DS9 scanner source and Python trajectory oracle.

This tool reads the maintained public store through its supported read-only
adapter.  It writes only replay fixtures beneath an explicitly supplied output
directory; it never writes to the scanner store.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from leo.analysis.persistent_hop_trajectory import (
    PersistentHopTrajectoryConfig,
    reconstruct_persistent_hop_trajectories,
)
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

SESSION = "scan-fw-3cfdaa6d75762cad"
TSV_HEADER = (
    "candidate_id\tsource_group_id\treceiver_id\tchannel\tedge\tactual_rf_hz\t"
    "support_start_utc_ns\tsupport_center_utc_ns\tsupport_end_utc_ns\t"
    "measured_cfo_hz\texact_score\tcontrol_score\tmargin\n"
)


def _generation(value: str) -> int:
    prefix = "adaptive-iio-"
    if not value.startswith(prefix):
        raise ValueError(f"unsupported stream generation: {value!r}")
    return int(value.removeprefix(prefix), 16)


def _projection_rows(source, projected):
    projected_by_binding = {
        (item.visit_index, item.receiver_id, item.probe_index, item.candidate_rank): item
        for item in projected
    }
    timing = source.timing
    assert timing is not None
    next_start: dict[tuple[int, int], int] = {}
    generation = _generation(source.stream_generation)
    for probe in sorted(
        source.probes, key=lambda item: (item.visit_index, item.receiver_id, item.probe_start_ms)
    ):
        key = probe.visit_index, probe.receiver_id
        if probe.probe_start_ms < next_start.get(key, -1):
            continue
        next_start[key] = probe.probe_start_ms + source.probe_ms
        offset = probe.probe_start_ms * source.sample_rate_hz // 1000
        source_row = {
            "input_digest": source.input_manifest_sha256,
            "analysis_digest": source.analysis_manifest_sha256,
            "generation": generation,
            "anchor_counter": timing.session_start_device_sample_counter,
            "anchor_utc_ns": timing.first_sample_estimate_utc_ns,
            "window_counter": probe.valid_start_counter + offset,
            "visit": probe.visit_index,
            "rate": source.sample_rate_hz,
            "probe_index": probe.probe_index,
            "receiver": probe.receiver_id,
            "channel": probe.channel,
            "upper_edge": probe.edge == "upper",
            "actual_rf_hz": probe.actual_rf_hz,
            "utc_bracket_width_ns": timing.first_sample_bracket_width_ns,
            "continuity_qualified": source.qualified,
        }
        for candidate in probe.candidates:
            expected = projected_by_binding.get(
                (probe.visit_index, probe.receiver_id, probe.probe_index, candidate.candidate_rank)
            )
            yield {
                "source": source_row,
                "candidate": {
                    "rank": candidate.candidate_rank,
                    "integer_epoch": candidate.integer_epoch_sample,
                    "fractional_offset": candidate.fractional_epoch_offset_samples,
                    "tracking_cfo_hz": candidate.fractional_tracking_cfo_hz,
                    "exact_score": candidate.fractional_exact_score,
                    "control_score": candidate.fractional_control_score,
                    "margin": candidate.fractional_margin,
                    "complete": candidate.passed_fractional_margin_gate,
                },
                "expected": (
                    None
                    if expected is None
                    else {
                        "candidate_id": expected.candidate_id,
                        "source_group_id": expected.source_group_id,
                        "support_start_utc_ns": expected.support_start_utc_ns,
                        "support_center_utc_ns": expected.support_center_utc_ns,
                        "support_end_utc_ns": expected.support_end_utc_ns,
                        "standard_uncertainty_hz": expected.standard_uncertainty_hz,
                        "factorial_support_moments_s": expected.factorial_support_moments_s,
                    }
                ),
            }


def export(root: Path, session: str, output: Path) -> None:
    store = ScannerTrackingInputStore(root)
    try:
        source = store.load(session)
    finally:
        store.close()
    projected = project_scanner_candidates(source)
    config = PersistentHopTrajectoryConfig(minimum_span_s=3.0, minimum_support=6)
    trajectory = reconstruct_persistent_hop_trajectories(projected, config=config)

    output.mkdir(parents=True, exist_ok=True)
    with (output / "candidates.tsv").open("w", encoding="utf-8", newline="") as handle:
        handle.write(TSV_HEADER)
        for item in projected:
            handle.write(
                "\t".join(
                    (
                        item.candidate_id,
                        item.source_group_id,
                        str(item.receiver_id),
                        str(item.channel),
                        item.edge.value,
                        repr(item.actual_rf_hz),
                        str(item.support_start_utc_ns),
                        str(item.support_center_utc_ns),
                        str(item.support_end_utc_ns),
                        repr(item.measured_cfo_hz),
                        repr(item.exact_score),
                        repr(item.control_score),
                        repr(item.margin),
                    )
                )
                + "\n"
            )

    with (output / "graph-candidates.tsv").open("w", encoding="utf-8", newline="") as handle:
        handle.write(
            f"META\t{source.session_id}\t{source.input_manifest_sha256}\t"
            f"{source.timing.first_sample_estimate_utc_ns}\n"
        )
        handle.write(
            "candidate_id\tsupport_start_utc_ns\tsupport_center_utc_ns\t"
            "support_end_utc_ns\tmoment0\tmoment1\tmoment2\tmoment3\n"
        )
        for item in projected:
            handle.write(
                "\t".join(
                    (
                        item.candidate_id,
                        str(item.support_start_utc_ns),
                        str(item.support_center_utc_ns),
                        str(item.support_end_utc_ns),
                        *(repr(value) for value in item.factorial_support_moments_s),
                    )
                )
                + "\n"
            )

    projection_count = 0
    with (output / "projection-inputs.jsonl").open("w", encoding="utf-8") as handle:
        for row in _projection_rows(source, projected):
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
            projection_count += 1

    tracks = []
    for track in trajectory.tracklets:
        tracks.append(
            {
                "tracklet_id": track.tracklet_id,
                "lane_key": [
                    track.lane_key[0],
                    track.lane_key[1].value,
                    track.lane_key[2],
                    track.lane_key[3],
                ],
                "start_utc_ns": track.start_utc_ns,
                "end_utc_ns": track.end_utc_ns,
                "reference_utc_ns": track.reference_utc_ns,
                "normalized_rate_hz_per_s": track.normalized_rate_hz_per_s,
                "normalized_intercept_hz": track.normalized_intercept_hz,
                "residual_rms_hz": track.residual_rms_hz,
                "residual_max_hz": track.residual_max_hz,
                "weighted_support": track.weighted_support,
                "points": [asdict(point) for point in track.points],
            }
        )
    oracle = {
        "session_id": source.session_id,
        "input_manifest_sha256": source.input_manifest_sha256,
        "analysis_manifest_sha256": source.analysis_manifest_sha256,
        "config_digest": trajectory.config_digest,
        "projected_candidate_count": len(projected),
        "source_projection_row_count": projection_count,
        "track_count": len(tracks),
        "used_candidate_count": trajectory.used_candidate_count,
        "tracks": tracks,
    }
    (output / "oracle-tracks.json").write_text(
        json.dumps(oracle, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({key: oracle[key] for key in oracle if key != "tracks"}, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--session", default=SESSION)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export(args.root, args.session, args.output)


if __name__ == "__main__":
    main()
