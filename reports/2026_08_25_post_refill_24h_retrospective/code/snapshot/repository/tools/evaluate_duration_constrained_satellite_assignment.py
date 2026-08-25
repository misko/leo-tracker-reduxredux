#!/usr/bin/env python3
"""Extract duration-audited branch/probe data for satellite association.

This is a read-only research adapter over persisted Standard products.  It does
not identify a satellite and it deliberately does not promote a fitted CFO
trajectory to coherent frame evidence.  Its output has one row per canonical
branch and scheduled 20 ms source probe.  Final-bank integer CFO lifts are
collapsed because a fitted constant CFO makes those lifts nuisance-equivalent.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from leo.contracts.digests import canonical_digest  # type: ignore[import-untyped]

TARGET_SESSION_ID = "cap-20260824T192531-491832825b97"
TARGET_RUN_ID = "capture-f75a853e526844e29893f125d4a58940"
TARGET_SCOPE_DIGEST = "sha256:0e14f83ecfa8cab0a9d01a2b4ba1167c8a37ff1f815908b6dae8a5451fdcdb7f"
TARGET_STREAM_ID = "stream-1"
TARGET_RADIO_ID = "radio_pluto_19f2"
TARGET_RECEIVER_ID = 1
TARGET_SKY_FREQUENCY_HZ = 11_190_312_500

DEFAULT_RECORDING_MANIFEST = Path(
    f"/srv/bulk/leo/recordings/2026/08/24/{TARGET_SESSION_ID}/manifest.json"
)
DEFAULT_SCIENTIFIC_ROOT = Path(
    "/srv/bulk/leo/analysis/"
    f"{TARGET_SESSION_ID}/{TARGET_RUN_ID}/scientific/path-standard/{TARGET_SCOPE_DIGEST}"
)

PRODUCT_NAMES = {
    "schedule": "standard.probe-schedule.v2.json",
    "scan": "standard.pilot-scan.v3.json",
    "alias_map": "standard.cfo-alias-map.v2.json",
    "dealiased_bank": "standard.dealiased-trajectory-bank.v4.json",
    "final_bank": "standard.final-trajectory-bank.v3.json",
    "frame_segments": "standard.pilot-doppler-segments.v1.json",
    "path_report": "standard.path-report.v2.json",
}


@dataclass(frozen=True, slots=True)
class SourceCandidate:
    observation_id: str
    sample_start: int
    detection_time_s: float
    rank: int
    local_epoch_sample: int
    tracking_cfo_hz: float
    exact_score: float
    control_score: float | None
    margin: float
    qam_accuracy: float | None

    @property
    def selection_key(self) -> tuple[float, float, int, float, str]:
        return (
            self.margin,
            self.exact_score,
            -self.rank,
            -abs(self.tracking_cfo_hz),
            self.observation_id,
        )


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recording-manifest", type=Path, default=DEFAULT_RECORDING_MANIFEST)
    parser.add_argument("--scientific-root", type=Path, default=DEFAULT_SCIENTIFIC_ROOT)
    parser.add_argument("--session-id", default=TARGET_SESSION_ID)
    parser.add_argument("--stream-id", default=TARGET_STREAM_ID)
    parser.add_argument("--radio-id", default=TARGET_RADIO_ID)
    parser.add_argument("--receiver-id", type=int, default=TARGET_RECEIVER_ID)
    parser.add_argument(
        "--expected-sky-frequency-hz",
        type=int,
        default=TARGET_SKY_FREQUENCY_HZ,
    )
    parser.add_argument("--minimum-duration-s", type=float, default=1.0)
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="omit per-probe rows while retaining their counts and duration evidence",
    )
    parser.add_argument(
        "--allow-missing-empty-no-result-frame-segments",
        action="store_true",
        help=("accept a missing frame receipt only for a lineage-complete empty no-result path"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="write JSON here instead of stdout; paths below /mnt/qnap01 are refused",
    )
    return parser.parse_args()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return value


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _require_version(document: dict[str, Any], version: int, algorithm: str) -> None:
    if document.get("schema_version") != version or document.get("algorithm_version") != algorithm:
        raise ValueError(f"expected {algorithm} schema V{version}")


def _glrt_score(candidate: dict[str, Any]) -> dict[str, Any]:
    scores = [item for item in candidate.get("scores", ()) if item.get("method") == "glrt64"]
    if len(scores) != 1:
        raise ValueError("pilot candidate does not contain exactly one GLRT64 score")
    return scores[0]


def _source_candidates(scan: dict[str, Any]) -> dict[str, SourceCandidate]:
    _require_version(scan, 3, "standard-pilot-scan-v3")
    if scan.get("frequency_coordinate") != "baseband_cfo_hz":
        raise ValueError("pilot scan is not in the baseband CFO coordinate")
    if scan.get("frequency_reference") != "uncalibrated_prior":
        raise ValueError("pilot scan unexpectedly claims calibrated frequency authority")
    result: dict[str, SourceCandidate] = {}
    previous_start = -1
    for detection in scan.get("detections", ()):
        sample_start = int(detection["sample_start"])
        if sample_start <= previous_start:
            raise ValueError("pilot detections are not uniquely sample-ordered")
        previous_start = sample_start
        for expected_rank, candidate in enumerate(detection.get("candidates", ())):
            rank = int(candidate["rank"])
            if rank != expected_rank:
                raise ValueError("pilot candidate ranks are not contiguous from zero")
            score = _glrt_score(candidate)
            observation_id = canonical_digest(
                {
                    "sample_start": sample_start,
                    "candidate_rank": rank,
                    "method": "glrt64",
                }
            )
            if observation_id in result:
                raise ValueError("pilot source observation identity is not unique")
            control = score.get("control_score")
            result[observation_id] = SourceCandidate(
                observation_id=observation_id,
                sample_start=sample_start,
                detection_time_s=_finite_number(detection["time_s"], "detection time"),
                rank=rank,
                local_epoch_sample=int(candidate["local_epoch_sample"]),
                tracking_cfo_hz=_finite_number(score["tracking_cfo_hz"], "tracking CFO"),
                exact_score=_finite_number(score["exact_score"], "exact score"),
                control_score=(
                    None if control is None else _finite_number(control, "control score")
                ),
                margin=_finite_number(score["margin"], "GLRT margin"),
                qam_accuracy=(
                    None
                    if candidate.get("qam_accuracy") is None
                    else _finite_number(candidate["qam_accuracy"], "QAM accuracy")
                ),
            )
    return result


def _stream_binding(
    manifest: dict[str, Any],
    raw_report: dict[str, Any],
    *,
    manifest_path: Path,
    session_id: str,
    stream_id: str,
    radio_id: str,
    receiver_id: int,
    expected_sky_frequency_hz: int,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, int]]:
    identities = (
        manifest.get("session_id"),
        raw_report.get("session_id"),
        raw_report.get("stream_id"),
        raw_report.get("radio_id"),
        raw_report.get("receiver_id"),
    )
    expected = (session_id, session_id, stream_id, radio_id, receiver_id)
    if identities != expected:
        raise ValueError(f"capture/path identity mismatch: observed={identities!r}")
    manifest_digest = _file_digest(manifest_path)
    if raw_report.get("manifest_digest") != manifest_digest:
        raise ValueError("path report does not bind the supplied recording manifest")

    streams = [
        item
        for item in manifest.get("streams", ())
        if item.get("stream_id") == stream_id and item.get("radio", {}).get("radio_id") == radio_id
    ]
    if len(streams) != 1:
        raise ValueError("recording manifest does not contain exactly one requested stream/radio")
    stream = streams[0]
    settings = stream.get("applied_settings") or stream.get("requested_settings")
    if not isinstance(settings, dict):
        raise ValueError("recording stream has no applied/requested settings")
    if receiver_id not in settings.get("receiver_ids", ()):
        raise ValueError("requested receiver is absent from the stream settings")

    sample_rate_hz = int(settings["sample_rate_hz"])
    declared_sample_count = int(raw_report["declared_sample_count"])
    if sample_rate_hz != int(raw_report["sample_rate_hz"]) or declared_sample_count != int(
        stream["captured_sample_count"]
    ):
        raise ValueError("manifest and path-report sample geometry disagree")

    prefix = f"tuning:{stream_id}:"
    tuning_tags = [tag for tag in manifest.get("tags", ()) if tag.startswith(prefix)]
    if len(tuning_tags) != 1:
        raise ValueError("manifest does not carry exactly one per-stream tuning tag")
    tag_parts = tuning_tags[0].split(":")
    valid_channels = {f"ch{index}" for index in range(1, 9)}
    if (
        len(tag_parts) != 4
        or tag_parts[2] not in valid_channels
        or tag_parts[3] not in {"lower", "upper"}
    ):
        raise ValueError("target stream has an invalid tuning channel/edge tag")

    profile = manifest["capture_plan"]["profile_revision"]["profile"]
    lnb_lo_hz = int(profile["lnb_lo_hz"])
    baseband_center_hz = int(settings["center_frequency_hz"])
    sky_frequency_hz = lnb_lo_hz + baseband_center_hz
    if sky_frequency_hz != expected_sky_frequency_hz:
        raise ValueError(
            f"applied sky frequency is {sky_frequency_hz}, expected {expected_sky_frequency_hz}"
        )

    timing = raw_report["timing"]
    stream_timing = stream.get("timing")
    if stream_timing is None:
        raise ValueError("stream has no UTC timing evidence")
    expected_timing = {
        "schema_version": 1,
        "first_estimate_utc_ns": stream_timing["first_sample"]["estimate_utc_ns"],
        "first_earliest_utc_ns": stream_timing["first_sample"]["earliest_utc_ns"],
        "first_latest_utc_ns": stream_timing["first_sample"]["latest_utc_ns"],
        "last_estimate_utc_ns": stream_timing["last_sample"]["estimate_utc_ns"],
        "last_earliest_utc_ns": stream_timing["last_sample"]["earliest_utc_ns"],
        "last_latest_utc_ns": stream_timing["last_sample"]["latest_utc_ns"],
    }
    if timing != expected_timing:
        raise ValueError("manifest and path-report timing evidence disagree")

    capture = {
        "session_id": session_id,
        "stream_id": stream_id,
        "radio_id": radio_id,
        "radio_serial": stream["radio"]["serial"],
        "receiver_id": receiver_id,
        "recording_manifest_digest": manifest_digest,
        "sample_rate_hz": sample_rate_hz,
        "declared_sample_count": declared_sample_count,
        "observed_sample_count": int(raw_report["observed_sample_count"]),
        "coverage_fraction": _finite_number(raw_report["coverage_fraction"], "coverage"),
    }
    frequency = {
        "lnb_lo_hz": lnb_lo_hz,
        "applied_baseband_center_hz": baseband_center_hz,
        "sky_frequency_hz": sky_frequency_hz,
        "tuning_tag": tuning_tags[0],
        "tuning_evidence_source": "per_stream_manifest_tag",
        "profile_nominal_sky_frequency_hz": profile.get("rf_center_frequency_hz"),
        "profile_nominal_matches_applied": profile.get("rf_center_frequency_hz")
        == sky_frequency_hz,
        "measurement_coordinate": "baseband_cfo_hz",
        "measurement_reference": raw_report["frequency_reference"],
        "requires_fitted_constant_cfo_per_satellite": True,
    }
    return (
        capture,
        frequency,
        {key: int(value) for key, value in timing.items() if key != "schema_version"},
    )


def _utc_ns(timing: dict[str, int], sample: int, declared_sample_count: int) -> dict[str, int]:
    last_sample = declared_sample_count - 1
    if not 0 <= sample <= last_sample:
        raise ValueError(f"sample {sample} lies outside the declared stream")

    def interpolate(prefix: str) -> int:
        first = timing[f"first_{prefix}_utc_ns"]
        last = timing[f"last_{prefix}_utc_ns"]
        return first + round((last - first) * sample / last_sample)

    return {
        "earliest_utc_ns": interpolate("earliest"),
        "estimate_utc_ns": interpolate("estimate"),
        "latest_utc_ns": interpolate("latest"),
    }


def _schedule(schedule: dict[str, Any]) -> tuple[dict[int, dict[str, Any]], dict[int, int]]:
    _require_version(schedule, 2, "standard-probe-schedule-v2")
    probes = schedule.get("probes", ())
    if len(probes) != int(schedule["returned_probe_count"]):
        raise ValueError("probe schedule accounting is inconsistent")
    by_sample: dict[int, dict[str, Any]] = {}
    ordinal: dict[int, int] = {}
    for index, probe in enumerate(probes):
        sample_start = int(probe["sample_start"])
        if sample_start in by_sample:
            raise ValueError("probe schedule sample starts are not unique")
        by_sample[sample_start] = probe
        ordinal[sample_start] = index
    if tuple(by_sample) != tuple(sorted(by_sample)):
        raise ValueError("probe schedule is not ordered")
    return by_sample, ordinal


def _scheduled_probe_rows(
    *,
    scan: dict[str, Any],
    schedule_by_sample: dict[int, dict[str, Any]],
    schedule_ordinal: dict[int, int],
    declared_sample_count: int,
    timing: dict[str, int],
) -> list[dict[str, Any]]:
    """Preserve native cadence, including probes with no retained candidate."""

    _require_version(scan, 3, "standard-pilot-scan-v3")
    detections_by_sample: dict[int, dict[str, Any]] = {}
    for detection in scan.get("detections", ()):
        sample_start = int(detection["sample_start"])
        if sample_start in detections_by_sample:
            raise ValueError("pilot scan detection sample starts are not unique")
        if sample_start not in schedule_by_sample:
            raise ValueError("pilot scan contains a detection outside the probe schedule")
        detections_by_sample[sample_start] = detection

    result = []
    for sample_start, probe in schedule_by_sample.items():
        detection = detections_by_sample.get(sample_start)
        if detection is not None and not math.isclose(
            float(detection["time_s"]), float(probe["time_s"]), rel_tol=0.0, abs_tol=1e-12
        ):
            raise ValueError("pilot scan detection time disagrees with its scheduled probe")
        retained_candidate_count = (
            len(detection.get("candidates", ())) if detection is not None else 0
        )
        source_candidate_count = (
            int(detection.get("source_candidate_count", retained_candidate_count))
            if detection is not None
            else 0
        )
        truncated_candidate_count = (
            int(detection.get("truncated_candidate_count", 0)) if detection is not None else 0
        )
        if (
            source_candidate_count < retained_candidate_count
            or truncated_candidate_count < 0
            or retained_candidate_count + truncated_candidate_count != source_candidate_count
        ):
            raise ValueError("pilot scan candidate accounting is inconsistent")
        status = str(detection.get("status", "complete")) if detection is not None else "absent"
        result.append(
            {
                "probe_id": probe["probe_id"],
                "schedule_ordinal": schedule_ordinal[sample_start],
                "coarse_window_index": int(probe["coarse_window_index"]),
                "subwindow_index": int(probe["subwindow_index"]),
                "probe_offset_ms": int(probe["probe_offset_ms"]),
                "probe_sample_start": sample_start,
                "probe_sample_count": int(probe["sample_count"]),
                "probe_start_time_s": float(probe["time_s"]),
                "probe_start_utc": _utc_ns(timing, sample_start, declared_sample_count),
                "scan_detection_present": detection is not None,
                "scan_status": status,
                "usable_for_activity": detection is not None
                and status in {"complete", "no_result"},
                "source_candidate_count": source_candidate_count,
                "retained_candidate_count": retained_candidate_count,
                "truncated_candidate_count": truncated_candidate_count,
            }
        )
    return result


def _alias_hypotheses(
    branch: dict[str, Any],
    final_rows: list[dict[str, Any]],
    alias_spacing_hz: float,
) -> list[dict[str, Any]]:
    model = branch["model"]
    canonical = tuple(float(value) for value in model["coefficients_hz"])
    result = []
    for row in sorted(
        final_rows, key=lambda item: (int(item["alias_index"]), item["trajectory_id"])
    ):
        if (
            row.get("branch_id") != branch["branch_id"]
            or row.get("component_id") != branch["component_id"]
            or row.get("canonical_model_id") != model["model_id"]
            or row.get("observation_ids") != branch["observation_ids"]
        ):
            raise ValueError("final CFO lift does not preserve canonical branch membership")
        observed_canonical = tuple(float(value) for value in row["canonical_coefficients_hz"])
        absolute = tuple(float(value) for value in row["absolute_coefficients_hz"])
        if observed_canonical != canonical or len(absolute) != len(canonical):
            raise ValueError("final CFO lift changes canonical branch geometry")
        if any(
            not math.isclose(left, right, rel_tol=0.0, abs_tol=1e-9)
            for left, right in zip(absolute[:-1], canonical[:-1], strict=True)
        ):
            raise ValueError("final CFO lift changes Doppler-rate coefficients")
        shift_hz = absolute[-1] - canonical[-1]
        expected_shift_hz = int(row["alias_index"]) * alias_spacing_hz
        if not math.isclose(shift_hz, expected_shift_hz, rel_tol=0.0, abs_tol=1e-6):
            raise ValueError("final CFO lift is not a constant integer-alias shift")
        result.append(
            {
                "trajectory_id": row["trajectory_id"],
                "alias_index": int(row["alias_index"]),
                "constant_cfo_shift_hz": shift_hz,
                "automatic_correction_eligible": bool(row["automatic_correction_eligible"]),
                "replay_tier": row["replay_tier"],
            }
        )
    return result


def _deduplicate_frame_windows(segments: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    _require_version(segments, 1, "standard-pilot-doppler-segments-v1")
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in segments.get("segments", ()):
        grouped[(row["source_branch_id"], int(row["source_probe_sample_start"]))].append(row)
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for (branch_id, sample_start), aliases in sorted(grouped.items()):
        intervals = {(float(row["start_time_s"]), float(row["end_time_s"])) for row in aliases}
        if len(intervals) != 1:
            raise ValueError("alias-expanded frame windows disagree on their interval")
        selected = min(
            aliases,
            key=lambda row: (
                not bool(row["qualified"]),
                -float(row["supported_frame_fraction"]),
                (
                    math.inf
                    if row.get("frequency_line_rms_hz") is None
                    else float(row["frequency_line_rms_hz"])
                ),
                row["source_trajectory_id"],
            ),
        )
        result[branch_id].append(
            {
                "source_probe_sample_start": sample_start,
                "start_time_s": float(selected["start_time_s"]),
                "end_time_s": float(selected["end_time_s"]),
                "qualified": any(bool(row["qualified"]) for row in aliases),
                "supported_frame_count": int(selected["supported_frame_count"]),
                "lattice_frame_count": int(selected["lattice_frame_count"]),
                "source_trajectory_ids": sorted({row["source_trajectory_id"] for row in aliases}),
                "collapsed_alias_window_count": len(aliases),
            }
        )
    return result


def _longest_interval_run(intervals: list[tuple[float, float]]) -> dict[str, Any] | None:
    if not intervals:
        return None
    ordered = sorted(intervals)
    runs: list[tuple[float, float, int]] = []
    start, end = ordered[0]
    count = 1
    for next_start, next_end in ordered[1:]:
        if next_start <= end + 1e-12:
            end = max(end, next_end)
            count += 1
        else:
            runs.append((start, end, count))
            start, end, count = next_start, next_end, 1
    runs.append((start, end, count))
    best = max(runs, key=lambda item: (item[1] - item[0], item[2], -item[0]))
    return {
        "start_s": best[0],
        "end_s": best[1],
        "duration_s": best[1] - best[0],
        "window_count": best[2],
    }


def _dense_probe_run(
    observations: list[dict[str, Any]], sample_rate_hz: int
) -> dict[str, Any] | None:
    if not observations:
        return None
    ordered = sorted(observations, key=lambda item: int(item["schedule_ordinal"]))
    runs: list[list[dict[str, Any]]] = [[ordered[0]]]
    for row in ordered[1:]:
        if int(row["schedule_ordinal"]) == int(runs[-1][-1]["schedule_ordinal"]) + 1:
            runs[-1].append(row)
        else:
            runs.append([row])

    def summary(run: list[dict[str, Any]]) -> dict[str, Any]:
        first = run[0]
        last = run[-1]
        start = int(first["probe_sample_start"])
        stop = int(last["probe_sample_start"]) + int(last["probe_sample_count"])
        return {
            "first_probe_id": first["probe_id"],
            "last_probe_id": last["probe_id"],
            "start_s": start / sample_rate_hz,
            "end_s": stop / sample_rate_hz,
            "elapsed_span_s": (stop - start) / sample_rate_hz,
            "integrated_probe_support_s": sum(int(item["probe_sample_count"]) for item in run)
            / sample_rate_hz,
            "probe_count": len(run),
        }

    summaries = [summary(run) for run in runs]
    return max(
        summaries,
        key=lambda item: (item["elapsed_span_s"], item["probe_count"], -item["start_s"]),
    )


def _branch_observations(
    branch: dict[str, Any],
    *,
    canonical_by_id: dict[str, dict[str, Any]],
    sources: dict[str, SourceCandidate],
    schedule_by_sample: dict[int, dict[str, Any]],
    schedule_ordinal: dict[int, int],
    sample_rate_hz: int,
    declared_sample_count: int,
    timing: dict[str, int],
) -> tuple[list[dict[str, Any]], int]:
    by_probe: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for observation_id in branch["observation_ids"]:
        canonical = canonical_by_id.get(observation_id)
        if canonical is None:
            raise ValueError("branch refers to a missing canonical observation")
        if canonical.get("source_trajectory_ids") != [branch["seed_trajectory_id"]]:
            raise ValueError("canonical observation does not preserve the branch seed trajectory")
        available = [
            sources[item] for item in canonical["source_observation_ids"] if item in sources
        ]
        if len(available) != len(canonical["source_observation_ids"]):
            raise ValueError("canonical observation source is absent from the pilot scan")
        source = max(available, key=lambda item: item.selection_key)
        if source.sample_start != int(canonical["sample_start"]):
            raise ValueError("canonical and source observations disagree on the probe")
        probe = schedule_by_sample.get(source.sample_start)
        if probe is None:
            raise ValueError("source observation is absent from the scheduled probes")
        if not math.isclose(
            float(probe["time_s"]), float(canonical["time_s"]), rel_tol=0.0, abs_tol=1e-12
        ):
            raise ValueError("canonical observation time disagrees with its scheduled probe")
        measurement_sample = source.sample_start + source.local_epoch_sample
        by_probe[probe["probe_id"]].append(
            {
                "branch_id": branch["branch_id"],
                "component_id": branch["component_id"],
                "seed_trajectory_id": branch["seed_trajectory_id"],
                "probe_id": probe["probe_id"],
                "probe_type": "scheduled_20ms_glrt64",
                "schedule_ordinal": schedule_ordinal[source.sample_start],
                "coarse_window_index": int(probe["coarse_window_index"]),
                "subwindow_index": int(probe["subwindow_index"]),
                "probe_offset_ms": int(probe["probe_offset_ms"]),
                "probe_sample_start": source.sample_start,
                "probe_sample_count": int(probe["sample_count"]),
                "probe_start_time_s": source.detection_time_s,
                "measurement_sample": measurement_sample,
                "measurement_time_s": measurement_sample / sample_rate_hz,
                "measurement_utc": _utc_ns(timing, measurement_sample, declared_sample_count),
                "canonical_observation_id": canonical["observation_id"],
                "source_observation_id": source.observation_id,
                "source_observation_ids": list(canonical["source_observation_ids"]),
                "source_trajectory_ids": list(canonical["source_trajectory_ids"]),
                "candidate_rank": source.rank,
                "local_epoch_sample": source.local_epoch_sample,
                "source_tracking_cfo_hz": source.tracking_cfo_hz,
                "component_cfo_hz": float(canonical["component_cfo_hz"]),
                "raw_cfo_hz": float(canonical["raw_cfo_hz"]),
                "residue_cfo_hz": float(canonical["residue_cfo_hz"]),
                "canonical_alias_index": int(canonical["alias_index"]),
                "glrt64_exact_score": source.exact_score,
                "glrt64_control_score": source.control_score,
                "glrt64_margin": source.margin,
                "qam_accuracy": source.qam_accuracy,
            }
        )

    collapsed_count = 0
    result = []
    for _probe_id, rows in sorted(
        by_probe.items(), key=lambda item: int(item[1][0]["probe_sample_start"])
    ):
        selected = max(
            rows,
            key=lambda row: (
                float(row["glrt64_margin"]),
                float(row["glrt64_exact_score"]),
                -int(row["candidate_rank"]),
                str(row["canonical_observation_id"]),
            ),
        )
        selected = dict(selected)
        selected["canonical_observation_ids"] = sorted(
            {row["canonical_observation_id"] for row in rows}
        )
        selected["collapsed_canonical_observation_count"] = len(rows)
        selected.pop("canonical_observation_id")
        collapsed_count += len(rows) - 1
        result.append(selected)
    return result, collapsed_count


def _require_complete_empty_no_result_without_frame_segments(
    *,
    paths: dict[str, Path],
    schedule: dict[str, Any],
    scan: dict[str, Any],
    alias_map: dict[str, Any],
    bank: dict[str, Any],
    final_bank: dict[str, Any],
    path_report: dict[str, Any],
) -> None:
    """Fail closed when an old empty Standard path lacks a frame receipt."""

    if not (
        alias_map.get("status") == "no_result"
        and alias_map.get("members") == []
        and alias_map.get("components") == []
        and int(alias_map.get("component_count", -1)) == 0
        and int(alias_map.get("source_representative_count", -1)) == 0
        and int(alias_map.get("returned_representative_count", -1)) == 0
        and int(alias_map.get("truncated_representative_count", -1)) == 0
    ):
        raise ValueError("missing frame receipt requires a complete empty no-result alias map")
    if not (
        bank.get("status") == "no_result"
        and bank.get("branches") == []
        and bank.get("observations") == []
        and int(bank.get("source_branch_count", -1)) == 0
        and int(bank.get("returned_branch_count", -1)) == 0
        and int(bank.get("truncated_branch_count", -1)) == 0
        and int(bank.get("source_observation_count", -1)) == 0
        and int(bank.get("returned_observation_count", -1)) == 0
        and int(bank.get("truncated_observation_count", -1)) == 0
    ):
        raise ValueError("missing frame receipt requires a complete empty no-result dealiased bank")
    if not (
        final_bank.get("status") == "no_result"
        and final_bank.get("trajectories") == []
        and int(final_bank.get("source_trajectory_count", -1)) == 0
        and int(final_bank.get("returned_trajectory_count", -1)) == 0
        and int(final_bank.get("truncated_trajectory_count", -1)) == 0
    ):
        raise ValueError("missing frame receipt requires a complete empty no-result final bank")
    if not (
        path_report.get("status") == "no_result"
        and path_report.get("final_trajectories") == []
        and int(path_report.get("source_trajectory_count", -1)) == 0
        and int(path_report.get("returned_trajectory_count", -1)) == 0
        and int(path_report.get("truncated_trajectory_count", -1)) == 0
    ):
        raise ValueError("missing frame receipt requires a complete empty no-result path report")
    if (
        path_report.get("cfo_alias_map_digest") != alias_map.get("content_digest")
        or path_report.get("dealiased_trajectory_bank_digest") != bank.get("content_digest")
        or path_report.get("final_trajectory_bank_digest") != final_bank.get("content_digest")
        or alias_map.get("pilot_scan_digest") != _file_digest(paths["scan"])
    ):
        raise ValueError("missing frame receipt has incomplete raw-product lineage")

    probes = schedule.get("probes")
    detections = scan.get("detections")
    if not isinstance(probes, list) or not (
        int(schedule.get("source_probe_count", -1))
        == int(schedule.get("returned_probe_count", -2))
        == len(probes)
        and int(schedule.get("truncated_probe_count", -1)) == 0
    ):
        raise ValueError("missing frame receipt requires a complete probe schedule")
    if not isinstance(detections, list) or len(detections) != len(probes):
        raise ValueError("missing frame receipt requires one pilot receipt per scheduled probe")
    if [int(item["sample_start"]) for item in detections] != [
        int(item["sample_start"]) for item in probes
    ]:
        raise ValueError("missing frame receipt pilot receipts do not cover the full schedule")
    for detection in detections:
        candidates = detection.get("candidates")
        if not isinstance(candidates, list) or not (
            detection.get("status") in {"complete", "no_result"}
            and int(detection.get("source_candidate_count", -1)) == len(candidates)
            and int(detection.get("truncated_candidate_count", -1)) == 0
        ):
            raise ValueError("missing frame receipt requires complete pilot candidate accounting")


def build_dataset(
    *,
    recording_manifest_path: Path,
    scientific_root: Path,
    session_id: str = TARGET_SESSION_ID,
    stream_id: str = TARGET_STREAM_ID,
    radio_id: str = TARGET_RADIO_ID,
    receiver_id: int = TARGET_RECEIVER_ID,
    expected_sky_frequency_hz: int = TARGET_SKY_FREQUENCY_HZ,
    minimum_duration_s: float = 1.0,
    allow_missing_empty_no_result_frame_segments: bool = False,
) -> dict[str, Any]:
    """Build one immutable in-memory extraction from persisted JSON products."""

    if not math.isfinite(minimum_duration_s) or minimum_duration_s <= 0.0:
        raise ValueError("minimum duration must be positive and finite")
    manifest = _read_json(recording_manifest_path)
    paths = {key: scientific_root / name for key, name in PRODUCT_NAMES.items()}
    missing_frame_segments = not paths["frame_segments"].is_file()
    if missing_frame_segments and not allow_missing_empty_no_result_frame_segments:
        raise ValueError("frame-segment source product is missing")
    products = {
        key: _read_json(path)
        for key, path in paths.items()
        if key != "frame_segments" or not missing_frame_segments
    }

    schedule = products["schedule"]
    scan = products["scan"]
    alias_map = products["alias_map"]
    bank = products["dealiased_bank"]
    final_bank = products["final_bank"]
    frame_segments = products.get("frame_segments")
    path_report = products["path_report"]
    _require_version(alias_map, 2, "cfo-alias-map-v2")
    _require_version(bank, 4, "hough-seeded-huber-linear-bank-v4")
    _require_version(final_bank, 3, "final-trajectory-bank-v3")
    _require_version(path_report, 2, "standard-path-report-v2")

    raw_report = path_report.get("raw_report")
    if not isinstance(raw_report, dict):
        raise ValueError("path report has no raw path authority")
    capture, frequency, timing = _stream_binding(
        manifest,
        raw_report,
        manifest_path=recording_manifest_path,
        session_id=session_id,
        stream_id=stream_id,
        radio_id=radio_id,
        receiver_id=receiver_id,
        expected_sky_frequency_hz=expected_sky_frequency_hz,
    )
    sample_rate_hz = int(capture["sample_rate_hz"])
    declared_sample_count = int(capture["declared_sample_count"])
    if int(schedule["sample_rate_hz"]) != sample_rate_hz:
        raise ValueError("probe schedule and capture sample rates disagree")
    if scan.get("probe_schedule_digest") != schedule.get("schedule_digest"):
        raise ValueError("pilot scan does not bind the supplied probe schedule")
    if raw_report.get("probe_schedule_digest") != schedule.get("schedule_digest"):
        raise ValueError("path report does not bind the supplied probe schedule")
    if bank.get("alias_map_digest") != alias_map.get("content_digest"):
        raise ValueError("dealiased bank does not bind the supplied alias map")
    if final_bank.get("dealiased_bank_digest") != bank.get("content_digest"):
        raise ValueError("final bank does not bind the supplied dealiased bank")
    if frame_segments is None:
        _require_complete_empty_no_result_without_frame_segments(
            paths=paths,
            schedule=schedule,
            scan=scan,
            alias_map=alias_map,
            bank=bank,
            final_bank=final_bank,
            path_report=path_report,
        )
    else:
        if frame_segments.get("dealiased_bank_digest") != bank.get("content_digest"):
            raise ValueError("frame segments do not bind the supplied dealiased bank")
        if frame_segments.get("final_trajectory_bank_digest") != final_bank.get("content_digest"):
            raise ValueError("frame segments do not bind the supplied final bank")

    schedule_by_sample, schedule_ordinal = _schedule(schedule)
    scheduled_probes = _scheduled_probe_rows(
        scan=scan,
        schedule_by_sample=schedule_by_sample,
        schedule_ordinal=schedule_ordinal,
        declared_sample_count=declared_sample_count,
        timing=timing,
    )
    sources = _source_candidates(scan)
    canonical_by_id = {item["observation_id"]: item for item in bank.get("observations", ())}
    if len(canonical_by_id) != len(bank.get("observations", ())):
        raise ValueError("canonical observations are not unique")
    final_by_branch: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in final_bank.get("trajectories", ()):
        final_by_branch[item["branch_id"]].append(item)
    frame_by_branch = {} if frame_segments is None else _deduplicate_frame_windows(frame_segments)

    member_component = {
        item["trajectory_id"]: item["component_id"] for item in alias_map.get("members", ())
    }
    alias_spacing_hz = float(alias_map["alias_spacing_numerator_hz"]) / float(
        alias_map["alias_spacing_denominator"]
    )
    branches = []
    collapsed_branch_probe_count = 0
    for branch in sorted(bank.get("branches", ()), key=lambda item: item["branch_id"]):
        if member_component.get(branch["seed_trajectory_id"]) != branch["component_id"]:
            raise ValueError("dealiased branch component disagrees with alias-map authority")
        observations, collapsed = _branch_observations(
            branch,
            canonical_by_id=canonical_by_id,
            sources=sources,
            schedule_by_sample=schedule_by_sample,
            schedule_ordinal=schedule_ordinal,
            sample_rate_hz=sample_rate_hz,
            declared_sample_count=declared_sample_count,
            timing=timing,
        )
        collapsed_branch_probe_count += collapsed
        aliases = _alias_hypotheses(
            branch, final_by_branch.get(branch["branch_id"], []), alias_spacing_hz
        )
        final_trajectory_ids = [item["trajectory_id"] for item in aliases]
        for observation in observations:
            observation["final_trajectory_ids"] = final_trajectory_ids
        dense_run = _dense_probe_run(observations, sample_rate_hz)
        source_span_s = (
            (
                int(observations[-1]["probe_sample_start"])
                + int(observations[-1]["probe_sample_count"])
                - int(observations[0]["probe_sample_start"])
            )
            / sample_rate_hz
            if observations
            else 0.0
        )
        windows = frame_by_branch.get(branch["branch_id"], ())
        qualified = [item for item in windows if item["qualified"]]
        qualified_run = _longest_interval_run(
            [(item["start_time_s"], item["end_time_s"]) for item in qualified]
        )
        dense_pass = bool(dense_run and dense_run["elapsed_span_s"] >= minimum_duration_s)
        integrated_probe_pass = bool(
            dense_run and dense_run["integrated_probe_support_s"] >= minimum_duration_s
        )
        frame_pass = bool(qualified_run and qualified_run["duration_s"] >= minimum_duration_s)
        frame_complete = (
            frame_segments is not None and int(frame_segments["truncated_track_count"]) == 0
        )
        if frame_pass:
            conclusion = "minimum_frame_coherence_demonstrated"
        elif dense_pass:
            conclusion = (
                "candidate_support_only_frame_evidence_incomplete"
                if not frame_complete
                else "candidate_support_only_frame_coherence_not_demonstrated"
            )
        else:
            conclusion = "below_dense_candidate_support_minimum"
        model = branch["model"]
        branches.append(
            {
                "branch_id": branch["branch_id"],
                "component_id": branch["component_id"],
                "seed_trajectory_id": branch["seed_trajectory_id"],
                "retained_by_final_bank": bool(aliases),
                "alias_hypotheses": aliases,
                "alias_hypothesis_count": len(aliases),
                "model": {
                    "model_id": model["model_id"],
                    "polynomial_degree": int(model["polynomial_degree"]),
                    "reference_time_s": float(model["reference_time_s"]),
                    "coefficients_hz": [float(value) for value in model["coefficients_hz"]],
                    "coefficient_order": "highest_polynomial_power_first",
                    "residual_rms_hz": float(model["residual_rms_hz"]),
                    "start_s": float(branch["start_s"]),
                    "end_s": float(branch["end_s"]),
                    "envelope_duration_s": float(branch["end_s"]) - float(branch["start_s"]),
                },
                "source_probe_count": len(observations),
                "source_probe_span_s": source_span_s,
                "longest_dense_20ms_probe_run": dense_run,
                "frame_coherence_evidence": {
                    "deduplicated_analyzed_window_count": len(windows),
                    "deduplicated_qualified_window_count": len(qualified),
                    "longest_contiguous_qualified_run": qualified_run,
                    "qualified_windows": qualified,
                    "complete_across_final_track_inventory": frame_complete,
                },
                "minimum_duration_evidence": {
                    "minimum_duration_s": minimum_duration_s,
                    "model_envelope_pass": float(branch["end_s"]) - float(branch["start_s"])
                    >= minimum_duration_s,
                    "source_probe_span_pass": source_span_s >= minimum_duration_s,
                    "dense_20ms_probe_run_span_pass": dense_pass,
                    "dense_20ms_integrated_support_pass": integrated_probe_pass,
                    "qualified_frame_run_pass": frame_pass,
                    "conclusion": conclusion,
                },
                "observations": observations,
            }
        )

    branch_ids = {item["branch_id"] for item in branches}
    orphan_final = sorted(set(final_by_branch) - branch_ids)
    if orphan_final:
        raise ValueError(f"final bank refers to unknown branches: {orphan_final!r}")
    components = []
    for item in alias_map.get("components", ()):
        component_branches = [
            branch["branch_id"]
            for branch in branches
            if branch["component_id"] == item["component_id"]
        ]
        component_probe_ids = {
            observation["probe_id"]
            for branch in branches
            if branch["component_id"] == item["component_id"]
            for observation in branch["observations"]
        }
        components.append(
            {
                "component_id": item["component_id"],
                "status": item["status"],
                "branch_ids": sorted(component_branches),
                "deduplicated_source_probe_count": len(component_probe_ids),
            }
        )

    unique_source_probe_ids = {
        observation["probe_id"] for branch in branches for observation in branch["observations"]
    }
    duration_summary = {
        "minimum_duration_s": minimum_duration_s,
        "branch_count": len(branches),
        "model_envelope_pass_branch_count": sum(
            bool(branch["minimum_duration_evidence"]["model_envelope_pass"]) for branch in branches
        ),
        "source_probe_span_pass_branch_count": sum(
            bool(branch["minimum_duration_evidence"]["source_probe_span_pass"])
            for branch in branches
        ),
        "dense_20ms_probe_run_span_pass_branch_count": sum(
            bool(branch["minimum_duration_evidence"]["dense_20ms_probe_run_span_pass"])
            for branch in branches
        ),
        "dense_20ms_integrated_support_pass_branch_count": sum(
            bool(branch["minimum_duration_evidence"]["dense_20ms_integrated_support_pass"])
            for branch in branches
        ),
        "qualified_frame_run_pass_branch_count": sum(
            bool(branch["minimum_duration_evidence"]["qualified_frame_run_pass"])
            for branch in branches
        ),
        "interpretation": (
            "20 ms run-span evidence is assignment support, not proof of continuous phase "
            "coherence across inter-probe gaps"
        ),
    }
    product_evidence = {
        key: {
            "path": str(path.resolve()),
            "file_digest": _file_digest(path),
            **(
                {"content_digest": products[key]["content_digest"]}
                if "content_digest" in products[key]
                else {}
            ),
        }
        for key, path in paths.items()
        if key in products
    }
    frame_inventory = (
        {
            "frame_evidence_available": False,
            "frame_evidence_unavailable_reason": (
                "sealed complete empty no-result path predates the frame-segment receipt"
            ),
            "missing_source_product": "standard.pilot-doppler-segments.v1.json",
            "alias_expanded_source_track_count": 0,
            "alias_expanded_analyzed_track_count": 0,
            "alias_expanded_truncated_track_count": 0,
            "alias_expanded_window_count": 0,
            "deduplicated_window_count": 0,
            "deduplicated_qualified_window_count": 0,
            "qualified_alias_expanded_window_count": 0,
            "evidence_complete": False,
            "absolute_carrier_phase_resolved": False,
            "frame_timing_is_receiver_relative": None,
        }
        if frame_segments is None
        else {
            "frame_evidence_available": True,
            "frame_evidence_unavailable_reason": None,
            "missing_source_product": None,
            "alias_expanded_source_track_count": int(frame_segments["source_track_count"]),
            "alias_expanded_analyzed_track_count": int(frame_segments["analyzed_track_count"]),
            "alias_expanded_truncated_track_count": int(frame_segments["truncated_track_count"]),
            "alias_expanded_window_count": int(frame_segments["analyzed_segment_count"]),
            "deduplicated_window_count": sum(len(value) for value in frame_by_branch.values()),
            "deduplicated_qualified_window_count": sum(
                bool(item["qualified"]) for windows in frame_by_branch.values() for item in windows
            ),
            "qualified_alias_expanded_window_count": int(frame_segments["qualified_segment_count"]),
            "evidence_complete": int(frame_segments["truncated_track_count"]) == 0,
            "absolute_carrier_phase_resolved": bool(
                frame_segments["absolute_carrier_phase_resolved"]
            ),
            "frame_timing_is_receiver_relative": bool(
                frame_segments["frame_timing_is_receiver_relative"]
            ),
        }
    )
    return {
        "schema": "org.leo.research.duration-constrained-satellite-assignment-input/v1",
        "candidate_only": True,
        "satellite_specificity_claimed": False,
        "capture": capture,
        "frequency_binding": frequency,
        "timing_binding": {
            **timing,
            "observation_utc_method": (
                "linear interpolation between manifest first/last sample timing anchors"
            ),
            "receiver_relative_time_origin": "first captured sample",
        },
        "probe_geometry": {
            "assignment_unit": "scheduled_20ms_glrt64_probe",
            "probe_duration_s": int(scan["probe_samples"]) / sample_rate_hz,
            "scheduled_probe_count": int(schedule["returned_probe_count"]),
            "scheduled_usable_probe_count": sum(
                bool(probe["usable_for_activity"]) for probe in scheduled_probes
            ),
            "scheduled_empty_candidate_probe_count": sum(
                bool(probe["usable_for_activity"]) and int(probe["retained_candidate_count"]) == 0
                for probe in scheduled_probes
            ),
            "scheduled_unusable_probe_count": sum(
                not bool(probe["usable_for_activity"]) for probe in scheduled_probes
            ),
            "pilot_detection_count": len(scan.get("detections", ())),
            "pilot_candidate_count": len(sources),
            "per_frame_assignment_available": False,
            "per_frame_note": (
                "1.333 ms frames occur inside separate bounded tracking products; "
                "the persisted source schedule assigns 20 ms detection probes"
            ),
        },
        "alias_collapse": {
            "final_trajectory_hypothesis_count": len(final_bank.get("trajectories", ())),
            "deduplicated_branch_count": len(branches),
            "alias_component_count": len(components),
            "alias_spacing_hz": alias_spacing_hz,
            "safe_under_fitted_constant_cfo": True,
            "components_are_satellite_identifications": False,
            "reason": (
                "each retained integer lift changes only the constant coefficient; "
                "Doppler-rate coefficients and source-probe membership are unchanged"
            ),
        },
        "source_completeness": {
            "raw_activity_inventory_complete": True,
            "frame_evidence_available": frame_segments is not None,
            "missing_source_products": (
                ["standard.pilot-doppler-segments.v1.json"] if frame_segments is None else []
            ),
        },
        "frame_evidence_inventory": frame_inventory,
        "counts": {
            "canonical_observation_count": len(canonical_by_id),
            "branch_probe_observation_count": sum(
                int(branch["source_probe_count"]) for branch in branches
            ),
            "collapsed_duplicate_branch_probe_count": collapsed_branch_probe_count,
            "unique_source_probe_count_across_branches": len(unique_source_probe_ids),
        },
        "duration_constraint_summary": duration_summary,
        "alias_components": components,
        "scheduled_probes": scheduled_probes,
        "branches": branches,
        "source_products": product_evidence,
    }


def _refuse_qnap_output(path: Path) -> None:
    resolved = path.resolve(strict=False)
    if resolved == Path("/mnt/qnap01") or Path("/mnt/qnap01") in resolved.parents:
        raise ValueError("this read-only evaluator refuses output beneath /mnt/qnap01")


def main() -> int:
    arguments = _arguments()
    document = build_dataset(
        recording_manifest_path=arguments.recording_manifest,
        scientific_root=arguments.scientific_root,
        session_id=arguments.session_id,
        stream_id=arguments.stream_id,
        radio_id=arguments.radio_id,
        receiver_id=arguments.receiver_id,
        expected_sky_frequency_hz=arguments.expected_sky_frequency_hz,
        minimum_duration_s=arguments.minimum_duration_s,
        allow_missing_empty_no_result_frame_segments=(
            arguments.allow_missing_empty_no_result_frame_segments
        ),
    )
    if arguments.summary_only:
        for branch in document["branches"]:
            branch["observations"] = []
        document["scheduled_probes"] = []
        document["per_probe_rows_omitted"] = True
    rendered = json.dumps(document, indent=2, sort_keys=True) + "\n"
    if arguments.output is None:
        sys.stdout.write(rendered)
    else:
        _refuse_qnap_output(arguments.output)
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
