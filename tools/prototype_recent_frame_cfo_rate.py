#!/usr/bin/env python3
"""Compare longer frame-profile Doppler-rate fits on recent lossless dwells."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib.figure import Figure  # noqa: E402

from leo.analysis.qam import (  # noqa: E402
    PilotFrameCfoConfig,
    evaluate_edge_pilot_frame_cfo_likelihood,
)
from leo.analysis.research.frame_cfo_rate import (  # noqa: E402
    FrameCfoProfile,
    FrameCfoRateMethod,
    FrameCfoRateSearchConfig,
    fit_frame_cfo_rate,
)
from leo.analysis.starlink.local_doppler import stable_measurement_floats  # noqa: E402
from leo.analysis.starlink.templates import (  # noqa: E402
    FRAME_RATE_HZ,
    OFDM_SYMBOL_DURATION_S,
    StarlinkEdge,
)
from leo.contracts.cfo_dealias import (  # noqa: E402
    DealiasedTrajectoryBankV4,
    FinalTrajectoryBankV3,
)
from leo.contracts.digests import canonical_digest  # noqa: E402
from leo.contracts.recording import RecordingStreamV2  # noqa: E402
from leo.contracts.states import StreamState, TimingMethod  # noqa: E402
from leo.storage import PinnedLocalRoot, RecordingStore  # noqa: E402

DEFAULT_BULK_ROOT = Path("/srv/bulk/leo")
DEFAULT_INPUTS = Path("config/analysis/recent-frame-cfo-rate-v1.json")
DEFAULT_OUTPUT_ROOT = Path("reports/figures/2026_08_25_recent_frame_cfo_rate")
SYMBOL_ALIAS_SPACING_HZ = 1.0 / OFDM_SYMBOL_DURATION_S


@dataclass(frozen=True, slots=True)
class RawSource:
    source_id: str
    detection_time_s: float
    sample_start: int
    local_epoch_sample: int
    tracking_cfo_hz: float
    exact_score: float
    control_score: float
    margin: float


@dataclass(frozen=True, slots=True)
class BoundDwell:
    label: str
    sample_rate_hz: int
    analysis_start_s: float
    analysis_stop_s: float
    first_sample_utc_ns: int
    age_s: float
    frame_epoch_sample: int
    source: RawSource
    source_observation_alias_index: int
    source_bound_cfo_hz: float
    trajectory_alias_index: int
    trajectory_reference_time_s: float
    trajectory_coefficients_hz: tuple[float, ...]
    trajectory_id: str
    branch_id: str
    profiles: tuple[FrameCfoProfile, ...]
    frame_inventory: tuple[dict[str, object], ...]
    opportunity_count: int
    verified_refill_count: int

    def model_cfo_hz(self, time_s: float) -> float:
        local = time_s - self.trajectory_reference_time_s
        return float(np.polyval(self.trajectory_coefficients_hz, local))

    def model_rate_hz_s(self, time_s: float) -> float:
        derivative = np.polyder(np.asarray(self.trajectory_coefficients_hz, dtype=float))
        return float(np.polyval(derivative, time_s - self.trajectory_reference_time_s))

    def source_bound_origin_hz(self, time_s: float) -> float:
        return float(
            self.source_bound_cfo_hz
            + self.model_cfo_hz(time_s)
            - self.model_cfo_hz(self.source.detection_time_s)
        )


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=DEFAULT_BULK_ROOT)
    parser.add_argument("--inputs", type=Path, default=DEFAULT_INPUTS)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--maximum-frames",
        type=int,
        help="bounded smoke cap per dwell; requires a noncanonical output root",
    )
    return parser.parse_args()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return value


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            stable_measurement_floats(value),
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _validate_inputs(document: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    expected = {
        "schema",
        "selection_reference_utc_ns",
        "maximum_age_s",
        "profile_residual_half_width_hz",
        "profile_step_hz",
        "window_durations_ms",
        "dwells",
    }
    if set(document) != expected or document.get("schema") != (
        "org.leo.research.recent-frame-cfo-rate-inputs/v1"
    ):
        raise ValueError("unsupported or non-closed recent frame-CFO-rate input")
    reference = document["selection_reference_utc_ns"]
    if not isinstance(reference, int) or isinstance(reference, bool) or reference <= 0:
        raise ValueError("selection reference must be one positive UTC nanosecond value")
    finite_positive = (
        document["maximum_age_s"],
        document["profile_residual_half_width_hz"],
        document["profile_step_hz"],
    )
    if any(
        not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0
        for value in finite_positive
    ):
        raise ValueError("prototype numeric settings must be finite and positive")
    if float(document["maximum_age_s"]) > 43_200.0:
        raise ValueError("recent-dwell prototype cannot admit data older than 12 hours")
    durations = document["window_durations_ms"]
    if not isinstance(durations, list) or durations != sorted(set(durations)):
        raise ValueError("window durations must be one sorted unique list")
    if any(
        not isinstance(value, (int, float)) or value < 20.0 or value > 125.0 for value in durations
    ):
        raise ValueError("window durations must lie in [20, 125] ms")
    dwells = document["dwells"]
    if not isinstance(dwells, list) or len(dwells) < 2:
        raise ValueError("prototype requires at least two recent dwells")
    dwell_fields = {
        "label",
        "session_id",
        "run_id",
        "scope_id",
        "stream_id",
        "radio_id",
        "receiver_id",
        "edge",
        "branch_id",
        "trajectory_id",
        "analysis_start_s",
        "analysis_stop_s",
        "recording_manifest_sha256",
        "analysis_manifest_sha256",
        "pilot_scan_sha256",
        "dealiased_bank_sha256",
        "final_bank_sha256",
    }
    output = []
    for item in dwells:
        if not isinstance(item, dict) or set(item) != dwell_fields:
            raise ValueError("recent dwell fields are not closed")
        strings = tuple(
            key
            for key in dwell_fields
            if key not in {"receiver_id", "analysis_start_s", "analysis_stop_s"}
        )
        if any(not isinstance(item[key], str) or not item[key] for key in strings):
            raise ValueError("recent dwell identities and digests must be nonempty strings")
        if not isinstance(item["receiver_id"], int) or isinstance(item["receiver_id"], bool):
            raise ValueError("receiver ID must be an integer")
        StarlinkEdge(item["edge"])
        start, stop = float(item["analysis_start_s"]), float(item["analysis_stop_s"])
        if not math.isfinite(start) or not math.isfinite(stop) or not 0 <= start < stop <= 60:
            raise ValueError("recent dwell interval is invalid")
        output.append(item)
    labels = [item["label"] for item in output]
    if len(labels) != len(set(labels)):
        raise ValueError("recent dwell labels must be unique")
    return tuple(output)


def _glrt_score(candidate: dict[str, Any]) -> dict[str, Any]:
    matches = [score for score in candidate["scores"] if score["method"] == "glrt64"]
    if len(matches) != 1:
        raise ValueError("candidate does not contain exactly one GLRT64 score")
    return matches[0]


def _raw_sources(scan: dict[str, Any]) -> dict[str, RawSource]:
    if scan.get("schema_version") != 3:
        raise ValueError("recent frame-CFO-rate prototype requires pilot-scan V3")
    output = {}
    for detection in scan["detections"]:
        for candidate in detection["candidates"]:
            score = _glrt_score(candidate)
            source_id = canonical_digest(
                {
                    "sample_start": int(detection["sample_start"]),
                    "candidate_rank": int(candidate["rank"]),
                    "method": "glrt64",
                }
            )
            output[source_id] = RawSource(
                source_id=source_id,
                detection_time_s=float(detection["time_s"]),
                sample_start=int(detection["sample_start"]),
                local_epoch_sample=int(candidate["local_epoch_sample"]),
                tracking_cfo_hz=float(score["tracking_cfo_hz"]),
                exact_score=float(score["exact_score"]),
                control_score=float(score["control_score"]),
                margin=float(score["margin"]),
            )
    return output


def _complex_receiver(values: np.ndarray) -> np.ndarray:
    if values.ndim != 3 or values.shape[1:] != (1, 2):
        raise ValueError("one-receiver CI16 data must have shape (samples, 1, 2)")
    return np.asarray(
        (values[:, 0, 0].astype(float) + 1j * values[:, 0, 1].astype(float)) / (2**15),
        dtype=np.complex128,
    )


def _continuity_is_lossless(stream: RecordingStreamV2) -> bool:
    continuity = stream.continuity
    return bool(
        stream.state is StreamState.COMPLETE
        and stream.timing is not None
        and stream.timing.first_sample.method is TimingMethod.DEVICE_COUNTER_ANCHORED
        and continuity.sample_loss_observable
        and continuity.observed_sample_count == stream.captured_sample_count
        and continuity.device_span_sample_count == stream.captured_sample_count
        and continuity.segment_count == 1
        and continuity.gap_count == 0
        and continuity.missing_sample_count == 0
        and continuity.overflow_count == 0
        and continuity.enqueue_failure_count == 0
        and continuity.clipped_sample_count == 0
        and continuity.constant_iq_refill_count == 0
        and continuity.terminal_rejected_gap_count == 0
        and continuity.terminal_rejected_missing_sample_count == 0
        and continuity.terminal_rejected_overflow_count == 0
    )


def _product_paths(bulk_root: Path, item: dict[str, Any]) -> dict[str, Path]:
    root = (
        bulk_root
        / "analysis"
        / item["session_id"]
        / item["run_id"]
        / "scientific"
        / "path-standard"
        / item["scope_id"]
    )
    return {
        "analysis_manifest": bulk_root
        / "analysis"
        / item["session_id"]
        / item["run_id"]
        / "manifest.json",
        "pilot_scan": root / "standard.pilot-scan.v3.json",
        "dealiased_bank": root / "standard.dealiased-trajectory-bank.v4.json",
        "final_bank": root / "standard.final-trajectory-bank.v3.json",
    }


def _verify_products(paths: dict[str, Path], item: dict[str, Any]) -> None:
    for name, field in (
        ("analysis_manifest", "analysis_manifest_sha256"),
        ("pilot_scan", "pilot_scan_sha256"),
        ("dealiased_bank", "dealiased_bank_sha256"),
        ("final_bank", "final_bank_sha256"),
    ):
        if _sha256(paths[name]) != item[field]:
            raise ValueError(f"{name} digest disagrees with the frozen recent-dwell input")


def _bind_source(
    item: dict[str, Any],
    scan: dict[str, Any],
    dealiased: DealiasedTrajectoryBankV4,
    final: FinalTrajectoryBankV3,
) -> tuple[RawSource, int, object]:
    branch_matches = [
        branch for branch in dealiased.branches if branch.branch_id == item["branch_id"]
    ]
    trajectory_matches = [
        trajectory
        for trajectory in final.trajectories
        if trajectory.trajectory_id == item["trajectory_id"]
        and trajectory.branch_id == item["branch_id"]
    ]
    if len(branch_matches) != 1 or len(trajectory_matches) != 1:
        raise ValueError("frozen branch or final trajectory is absent or duplicated")
    branch, trajectory = branch_matches[0], trajectory_matches[0]
    if set(trajectory.observation_ids) != set(branch.observation_ids):
        raise ValueError("final trajectory membership disagrees with its dealiased branch")
    observations = {value.observation_id: value for value in dealiased.observations}
    sources = _raw_sources(scan)
    center_s = 0.5 * (float(item["analysis_start_s"]) + float(item["analysis_stop_s"]))
    candidates = []
    for observation_id in branch.observation_ids:
        observation = observations[observation_id]
        if len(observation.source_observation_ids) != 1:
            raise ValueError("canonical observation lacks one exact raw GLRT source")
        source = sources.get(observation.source_observation_ids[0])
        if source is None:
            raise ValueError("canonical raw GLRT source is absent from pilot scan")
        if observation.sample_start != source.sample_start or not math.isclose(
            observation.raw_cfo_hz,
            source.tracking_cfo_hz,
            rel_tol=0.0,
            abs_tol=1e-6,
        ):
            raise ValueError("canonical and raw GLRT source evidence disagrees")
        if abs(source.detection_time_s - center_s) <= 0.075:
            candidates.append((source, int(observation.alias_index)))
    if not candidates:
        raise ValueError("selected interval has no exact branch-bound GLRT epoch source")
    source, observation_alias = max(
        candidates,
        key=lambda value: (
            value[0].margin,
            value[0].exact_score,
            -abs(value[0].detection_time_s - center_s),
        ),
    )
    return source, observation_alias, trajectory


def _frame_starts(
    epoch_sample: int,
    sample_rate_hz: int,
    start_s: float,
    stop_s: float,
    frame_content: int,
) -> tuple[int, ...]:
    period = sample_rate_hz / FRAME_RATE_HZ
    first = math.ceil((start_s * sample_rate_hz - epoch_sample) / period)
    last = math.floor((stop_s * sample_rate_hz - frame_content - epoch_sample) / period)
    return tuple(epoch_sample + round(index * period) for index in range(first, last + 1))


def analyze_dwell(
    store: RecordingStore,
    bulk_root: Path,
    item: dict[str, Any],
    document: dict[str, Any],
    *,
    maximum_frames: int | None,
) -> BoundDwell:
    bundle = store.inspect(item["session_id"])
    if bundle.manifest_sha256 != item["recording_manifest_sha256"]:
        raise ValueError("recording manifest digest disagrees with the frozen input")
    stream_matches = [
        stream for stream in bundle.manifest.streams if stream.stream_id == item["stream_id"]
    ]
    if len(stream_matches) != 1 or not isinstance(stream_matches[0], RecordingStreamV2):
        raise ValueError("recent dwell requires one V2 recording stream")
    stream = stream_matches[0]
    if stream.radio.radio_id != item["radio_id"]:
        raise ValueError("recording radio identity disagrees with the frozen input")
    tuning_prefix = f"tuning:{item['stream_id']}:"
    tuning_tags = [tag for tag in bundle.manifest.tags if tag.startswith(tuning_prefix)]
    if len(tuning_tags) != 1 or tuning_tags[0].rsplit(":", maxsplit=1)[-1] != item["edge"]:
        raise ValueError("recording tuning edge disagrees with the frozen input")
    if not _continuity_is_lossless(stream):
        raise ValueError("recent dwell is not counter-authoritative and lossless")
    if stream.timing is None:
        raise ValueError("recent dwell has no first-sample timing")
    first_sample_utc_ns = stream.timing.first_sample.estimate_utc_ns
    age_s = (int(document["selection_reference_utc_ns"]) - first_sample_utc_ns) / 1e9
    if age_s < 0.0 or age_s > float(document["maximum_age_s"]):
        raise ValueError("dwell lies outside the frozen <=12-hour selection window")
    reader = store.reader(bundle, item["stream_id"], verify=True)
    if reader.sample_rate_hz != 2_500_000 or item["receiver_id"] not in reader.receiver_ids:
        raise ValueError("recent prototype requires the pinned 2.5 MS/s receiver")
    gap_map = reader.gap_map()
    if gap_map.segment_count != 1 or gap_map.missing_sample_count != 0:
        raise ValueError("gap map does not prove one lossless device-time segment")

    paths = _product_paths(bulk_root, item)
    _verify_products(paths, item)
    analysis_manifest = _load(paths["analysis_manifest"])
    if (
        analysis_manifest.get("session_id") != item["session_id"]
        or analysis_manifest.get("run_id") != item["run_id"]
    ):
        raise ValueError("analysis manifest identity disagrees with the frozen input")
    if analysis_manifest.get("pipeline_lane") != "standard":
        raise ValueError("recent frame-CFO-rate prototype requires a Standard analysis run")
    scan = _load(paths["pilot_scan"])
    dealiased = DealiasedTrajectoryBankV4.model_validate_json(paths["dealiased_bank"].read_bytes())
    final = FinalTrajectoryBankV3.model_validate_json(paths["final_bank"].read_bytes())
    source, observation_alias, trajectory = _bind_source(item, scan, dealiased, final)
    source_bound_cfo_hz = float(
        source.tracking_cfo_hz
        + (trajectory.alias_index - observation_alias) * SYMBOL_ALIAS_SPACING_HZ
    )
    model_at_source = float(
        np.polyval(
            trajectory.absolute_coefficients_hz,
            source.detection_time_s - trajectory.reference_time_s,
        )
    )
    if abs(source_bound_cfo_hz - model_at_source) > 2_000.0:
        raise ValueError("source-bound GLRT CFO leaves the selected final trajectory basin")

    sample_rate_hz = reader.sample_rate_hz
    frame_content = round(302 * sample_rate_hz * OFDM_SYMBOL_DURATION_S)
    starts = _frame_starts(
        source.sample_start + source.local_epoch_sample,
        sample_rate_hz,
        float(item["analysis_start_s"]),
        float(item["analysis_stop_s"]),
        frame_content,
    )
    if maximum_frames is not None:
        starts = starts[:maximum_frames]
    if len(starts) < 20:
        raise ValueError("selected recent interval has fewer than 20 complete frame opportunities")
    read_start = starts[0] - 1
    read_stop = starts[-1] + frame_content + 1
    device = reader.read_device_span(
        read_start,
        read_stop - read_start,
        receiver_ids=(int(item["receiver_id"]),),
    )
    samples = _complex_receiver(device.samples)
    residual_limit = float(document["profile_residual_half_width_hz"])
    residual_step = float(document["profile_step_hz"])
    grid = np.arange(-residual_limit, residual_limit + 0.5 * residual_step, residual_step)
    settings = PilotFrameCfoConfig(residual_half_width_hz=residual_limit)
    profiles = []
    inventory = []
    for frame_index, frame_start in enumerate(starts):
        local = frame_start - read_start
        local_slice = slice(local - 1, local + frame_content + 1)
        valid = device.valid_samples[local_slice]
        segment_ids = device.continuity_segment_ids[local_slice]
        continuity_safe = bool(np.all(valid) and len(set(segment_ids.tolist())) == 1)
        reference_time_s = (frame_start + 1672.0) / sample_rate_hz
        model_cfo = float(
            source_bound_cfo_hz
            + np.polyval(
                trajectory.absolute_coefficients_hz,
                reference_time_s - trajectory.reference_time_s,
            )
            - model_at_source
        )
        if not continuity_safe:
            inventory.append(
                {
                    "label": item["label"],
                    "frame_index": frame_index,
                    "frame_start_sample": frame_start,
                    "reference_time_s": reference_time_s,
                    "continuity_safe": False,
                    "training_supported": False,
                    "rejection_reasons": ["device_gap_or_segment_crossing"],
                    "even_absolute_cfo_hz": None,
                    "odd_absolute_cfo_hz": None,
                }
            )
            continue
        result = evaluate_edge_pilot_frame_cfo_likelihood(
            samples[local_slice],
            sample_rate_hz,
            frame_start_sample=frame_start,
            acquisition_absolute_cfo_hz=model_cfo,
            edge=item["edge"],
            residual_grid_hz=grid,
            config=settings,
        )
        split = result.split_validation
        inventory.append(
            {
                "label": item["label"],
                "frame_index": frame_index,
                "frame_start_sample": frame_start,
                "reference_time_s": reference_time_s,
                "continuity_safe": True,
                "training_supported": split.training_supported,
                "rejection_reasons": list(split.training_rejection_reasons),
                "even_absolute_cfo_hz": split.even_absolute_cfo_hz,
                "odd_absolute_cfo_hz": split.odd_absolute_cfo_hz,
            }
        )
        if not split.training_supported:
            continue
        profiles.append(
            FrameCfoProfile(
                frame_start_sample=frame_start,
                reference_time_s=reference_time_s,
                continuity_segment=int(segment_ids[0]),
                cfo_origin_hz=model_cfo,
                residual_grid_hz=result.residual_grid_hz,
                even_exact_log_likelihood=result.even_exact_log_likelihood,
                even_control_log_likelihood=result.even_control_log_likelihood,
                odd_exact_log_likelihood=result.odd_exact_log_likelihood,
                odd_control_log_likelihood=result.odd_control_log_likelihood,
            )
        )
    return BoundDwell(
        label=str(item["label"]),
        sample_rate_hz=sample_rate_hz,
        analysis_start_s=float(item["analysis_start_s"]),
        analysis_stop_s=float(item["analysis_stop_s"]),
        first_sample_utc_ns=first_sample_utc_ns,
        age_s=age_s,
        frame_epoch_sample=source.sample_start + source.local_epoch_sample,
        source=source,
        source_observation_alias_index=observation_alias,
        source_bound_cfo_hz=source_bound_cfo_hz,
        trajectory_alias_index=int(trajectory.alias_index),
        trajectory_reference_time_s=float(trajectory.reference_time_s),
        trajectory_coefficients_hz=tuple(
            float(value) for value in trajectory.absolute_coefficients_hz
        ),
        trajectory_id=str(trajectory.trajectory_id),
        branch_id=str(trajectory.branch_id),
        profiles=tuple(profiles),
        frame_inventory=tuple(inventory),
        opportunity_count=len(starts),
        verified_refill_count=int(stream.continuity.refill_count),
    )


def _window_rows(
    dwell: BoundDwell,
    durations_ms: tuple[float, ...],
) -> tuple[dict[str, object], ...]:
    methods = tuple(FrameCfoRateMethod)
    rows = []
    ordered = dwell.profiles
    for duration_ms in durations_ms:
        duration_s = duration_ms / 1_000.0
        nominal_count = round(duration_ms * FRAME_RATE_HZ / 1_000.0)
        block_count = math.floor(
            (dwell.analysis_stop_s - dwell.analysis_start_s) / duration_s + 1e-12
        )
        for block_index in range(block_count):
            block_start_s = dwell.analysis_start_s + block_index * duration_s
            block_stop_s = block_start_s + duration_s
            window = tuple(
                frame for frame in ordered if block_start_s <= frame.reference_time_s < block_stop_s
            )
            if len(window) < max(6, math.ceil(0.6 * nominal_count)):
                continue
            reference_time_s = float(np.mean([frame.reference_time_s for frame in window]))
            initial_cfo_hz = dwell.source_bound_origin_hz(reference_time_s)
            initial_rate_hz_s = dwell.model_rate_hz_s(reference_time_s)
            search = FrameCfoRateSearchConfig(
                minimum_frames=max(6, math.ceil(0.6 * nominal_count)),
                minimum_span_s=max(0.008, 0.6 * duration_s),
            )
            window_id = f"{dwell.label}-{duration_ms:g}ms-{block_index:04d}"
            for method in methods:
                fit = fit_frame_cfo_rate(
                    window,
                    initial_cfo_hz=initial_cfo_hz,
                    initial_rate_hz_s=initial_rate_hz_s,
                    method=method,
                    config=search,
                )
                row = asdict(fit)
                row["method"] = fit.method.value
                row.update(
                    {
                        "label": dwell.label,
                        "window_id": window_id,
                        "duration_ms": duration_ms,
                        "block_index": block_index,
                        "window_start_s": window[0].reference_time_s,
                        "window_stop_s": window[-1].reference_time_s,
                        "initial_glrt_rate_hz_s": initial_rate_hz_s,
                        "rate_delta_from_glrt_hz_s": fit.rate_hz_s - initial_rate_hz_s,
                    }
                )
                rows.append(row)
    return tuple(rows)


def _summaries(rows: tuple[dict[str, object], ...]) -> tuple[dict[str, object], ...]:
    groups: dict[tuple[str, float, str], list[dict[str, object]]] = {}
    for row in rows:
        key = (str(row["label"]), float(row["duration_ms"]), str(row["method"]))
        groups.setdefault(key, []).append(row)
    output = []
    for (label, duration_ms, method), values in sorted(groups.items()):
        counts = np.asarray([int(value["frame_count"]) for value in values], dtype=float)
        rms = np.asarray([float(value["odd_cfo_rms_hz"]) for value in values])
        rates = np.asarray([float(value["rate_hz_s"]) for value in values])
        sigmas = np.asarray(
            [
                float(value["conditional_rate_sigma_hz_s"])
                for value in values
                if value["conditional_rate_sigma_hz_s"] is not None
            ]
        )
        output.append(
            {
                "label": label,
                "duration_ms": duration_ms,
                "method": method,
                "window_count": len(values),
                "pooled_odd_cfo_rms_hz": float(np.sqrt(np.sum(counts * rms**2) / np.sum(counts))),
                "median_odd_cfo_rms_hz": float(np.median(rms)),
                "mean_odd_exact_log_likelihood_per_frame": float(
                    np.mean(
                        [
                            float(value["odd_exact_objective"]) / int(value["frame_count"])
                            for value in values
                        ]
                    )
                ),
                "median_rate_hz_s": float(np.median(rates)),
                "rate_mad_hz_s": float(np.median(np.abs(rates - np.median(rates)))),
                "median_conditional_rate_sigma_hz_s": (
                    float(np.median(sigmas)) if sigmas.size else None
                ),
                "median_odd_exact_minus_control": float(
                    np.median([float(value["odd_exact_minus_control"]) for value in values])
                ),
                "boundary_fraction": float(
                    np.mean(
                        [
                            bool(value["cfo_search_boundary"])
                            or bool(value["rate_search_boundary"])
                            for value in values
                        ]
                    )
                ),
            }
        )
    return tuple(output)


def _method_label(method: str) -> str:
    return {
        FrameCfoRateMethod.GLRT_RATE.value: "20 ms GLRT trend",
        FrameCfoRateMethod.FRAME_MAXIMA.value: "frame maxima + robust line",
        FrameCfoRateMethod.SUMMED_PROFILE.value: "summed frame profiles",
        FrameCfoRateMethod.OCCUPANCY_MIXTURE.value: "20% occupancy mixture",
    }[method]


def _plot(
    path: Path, summaries: tuple[dict[str, object], ...], rows: tuple[dict[str, object], ...]
) -> None:
    colors = {
        FrameCfoRateMethod.GLRT_RATE.value: "#777777",
        FrameCfoRateMethod.FRAME_MAXIMA.value: "#E69F00",
        FrameCfoRateMethod.SUMMED_PROFILE.value: "#0072B2",
        FrameCfoRateMethod.OCCUPANCY_MIXTURE.value: "#009E73",
    }
    durations = sorted({float(row["duration_ms"]) for row in summaries})
    methods = [method.value for method in FrameCfoRateMethod]
    labels = sorted({str(row["label"]) for row in summaries})
    complete_durations = [
        duration
        for duration in durations
        if all(
            any(
                row["label"] == label and row["duration_ms"] == duration and row["method"] == method
                for row in summaries
            )
            for label in labels
            for method in methods
        )
    ]
    if not complete_durations:
        raise ValueError("no comparison duration has every dwell and method")
    comparison_duration = max(complete_durations)
    figure = Figure(figsize=(13.5, 9.2), constrained_layout=True)
    axes = figure.subplots(2, 2)

    axis = axes[0, 0]
    for method in methods:
        y = []
        for duration in durations:
            values = [
                float(row["pooled_odd_cfo_rms_hz"])
                for row in summaries
                if row["method"] == method and row["duration_ms"] == duration
            ]
            y.append(float(np.mean(values)))
        axis.plot(
            durations, y, marker="o", linewidth=2, color=colors[method], label=_method_label(method)
        )
    axis.set_title("A  Odd-Qin prediction response")
    axis.set_xlabel("History (ms)")
    axis.set_ylabel("Equal-dwell mean RMS (Hz) · lower is better")
    axis.grid(alpha=0.25)
    axis.legend(fontsize=8)

    axis = axes[0, 1]
    width = 0.18
    x = np.arange(len(labels), dtype=float)
    for index, method in enumerate(methods):
        values = []
        for label in labels:
            current = next(
                row
                for row in summaries
                if row["label"] == label
                and row["duration_ms"] == comparison_duration
                and row["method"] == method
            )
            baseline = next(
                row
                for row in summaries
                if row["label"] == label
                and row["duration_ms"] == comparison_duration
                and row["method"] == FrameCfoRateMethod.GLRT_RATE.value
            )
            values.append(
                100.0
                * float(current["pooled_odd_cfo_rms_hz"])
                / float(baseline["pooled_odd_cfo_rms_hz"])
            )
        axis.bar(
            x + (index - 1.5) * width,
            values,
            width,
            color=colors[method],
            label=_method_label(method),
        )
    axis.axhline(100.0, color="black", linewidth=1, linestyle="--")
    axis.set_xticks(x, labels)
    axis.set_title(f"B  {comparison_duration:g} ms error relative to GLRT trend")
    axis.set_ylabel("Odd-Qin response RMS / GLRT RMS (%)")
    axis.grid(axis="y", alpha=0.25)

    axis = axes[1, 0]
    for method in (FrameCfoRateMethod.FRAME_MAXIMA.value, FrameCfoRateMethod.SUMMED_PROFILE.value):
        y = []
        for duration in durations:
            values = [
                float(row["median_conditional_rate_sigma_hz_s"])
                for row in summaries
                if row["method"] == method
                and row["duration_ms"] == duration
                and row["median_conditional_rate_sigma_hz_s"] is not None
            ]
            y.append(float(np.median(values)))
        axis.plot(
            durations, y, marker="o", linewidth=2, color=colors[method], label=_method_label(method)
        )
    axis.set_yscale("log")
    axis.set_title("C  Conditional rate precision")
    axis.set_xlabel("History (ms)")
    axis.set_ylabel("Conditional σ(rate) (Hz/s) · not coverage-calibrated")
    axis.grid(alpha=0.25, which="both")
    axis.legend(fontsize=8)

    axis = axes[1, 1]
    markers = {"D1": "o", "D2": "s", "D3": "^"}
    selected = [row for row in rows if float(row["duration_ms"]) == comparison_duration]
    for label in labels:
        for method in (FrameCfoRateMethod.GLRT_RATE.value, FrameCfoRateMethod.SUMMED_PROFILE.value):
            values = sorted(
                [row for row in selected if row["label"] == label and row["method"] == method],
                key=lambda row: float(row["reference_time_s"]),
            )
            axis.plot(
                [
                    float(row["reference_time_s"]) - float(values[0]["reference_time_s"])
                    for row in values
                ],
                [float(row["rate_hz_s"]) / 1_000.0 for row in values],
                marker=markers.get(label, "o"),
                markersize=3.5,
                linewidth=1.2,
                color=colors[method],
                alpha=0.45 if method == FrameCfoRateMethod.GLRT_RATE.value else 0.9,
                linestyle="--" if method == FrameCfoRateMethod.GLRT_RATE.value else "-",
                label=f"{label} · {_method_label(method)}",
            )
    axis.set_title(f"D  Non-overlapping {comparison_duration:g} ms rate estimates")
    axis.set_xlabel("Time within analyzed interval (s)")
    axis.set_ylabel("CFO rate (kHz/s)")
    axis.grid(alpha=0.25)
    axis.legend(fontsize=7, ncol=2)

    figure.suptitle(
        "Recent counter-authoritative dwells: longer noncoherent frame-CFO histories",
        fontsize=14,
    )
    figure.supxlabel(
        "Frame methods fit even Qin; their odd Qin and roll-17 controls are fit-withheld. "
        "The GLRT context slope used both parities upstream. Carrier phase is never "
        "connected. All 573 refills per dwell are counter-proven gap-free.",
        fontsize=8,
    )
    figure.savefig(path, dpi=180, metadata={"Software": "leo-tracker"})


def _write_csv(path: Path, rows: tuple[dict[str, object], ...]) -> None:
    if not rows:
        raise ValueError("cannot write an empty CSV")
    fields = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def run(
    *,
    bulk_root: Path,
    inputs_path: Path,
    output_root: Path,
    maximum_frames: int | None,
) -> dict[str, object]:
    document = _load(inputs_path)
    inputs = _validate_inputs(document)
    if maximum_frames is not None:
        if maximum_frames < 20:
            raise ValueError("smoke cap must retain at least 20 frames per dwell")
        if output_root.resolve() == DEFAULT_OUTPUT_ROOT.resolve():
            raise ValueError("a bounded smoke run cannot overwrite the canonical output root")
    output_root.mkdir(parents=True, exist_ok=True)
    store = RecordingStore.open_pinned(PinnedLocalRoot(bulk_root))
    try:
        dwells = tuple(
            analyze_dwell(
                store,
                bulk_root,
                item,
                document,
                maximum_frames=maximum_frames,
            )
            for item in inputs
        )
    finally:
        store.close()
    durations = tuple(float(value) for value in document["window_durations_ms"])
    rows = tuple(row for dwell in dwells for row in _window_rows(dwell, durations))
    summaries = _summaries(rows)
    frame_inventory = tuple(row for dwell in dwells for row in dwell.frame_inventory)

    csv_path = output_root / "window-fits.csv"
    frame_path = output_root / "frame-inventory.json"
    plot_path = output_root / "comparison.png"
    summary_path = output_root / "summary.json"
    manifest_path = output_root / "artifact-manifest.json"
    _write_csv(csv_path, rows)
    frame_path.write_bytes(_json_bytes(frame_inventory))
    _plot(plot_path, summaries, rows)
    summary: dict[str, object] = {
        "schema": "org.leo.research.recent-frame-cfo-rate-summary/v1",
        "candidate_only": True,
        "known_pilots_only": True,
        "carrier_phase_connected": False,
        "odd_qin_provenance": {
            "frame_profile_methods_odd_symbols_influenced_fit": False,
            "glrt_context_odd_symbols_influenced_upstream_rate": True,
            "comparison_label": ("odd-Qin response; fit-withheld only for frame-profile methods"),
        },
        "selection_reference_utc": datetime.fromtimestamp(
            int(document["selection_reference_utc_ns"]) / 1e9,
            tz=UTC,
        ).isoformat(),
        "maximum_age_s": document["maximum_age_s"],
        "full_frozen_run": maximum_frames is None,
        "continuity_policy": (
            "V2 device-counter anchored; one lossless segment; verified contiguous "
            "application refills"
        ),
        "input_sha256": _sha256(inputs_path),
        "implementation_sha256": {
            "tool": _sha256(Path(__file__)),
            "rate_model": _sha256(
                Path(__file__).parents[1] / "src/leo/analysis/research/frame_cfo_rate.py"
            ),
            "frame_profile": _sha256(Path(__file__).parents[1] / "src/leo/analysis/qam/pilot.py"),
        },
        "configuration": {
            "profile_residual_half_width_hz": document["profile_residual_half_width_hz"],
            "profile_step_hz": document["profile_step_hz"],
            "window_durations_ms": list(durations),
            "methods": [method.value for method in FrameCfoRateMethod],
            "occupancy_outlier_fraction": FrameCfoRateSearchConfig().occupancy_outlier_fraction,
        },
        "dwells": [
            {
                "label": dwell.label,
                "first_sample_utc": datetime.fromtimestamp(
                    dwell.first_sample_utc_ns / 1e9,
                    tz=UTC,
                ).isoformat(),
                "age_s": dwell.age_s,
                "opportunity_count": dwell.opportunity_count,
                "training_supported_count": len(dwell.profiles),
                "training_retention": len(dwell.profiles) / dwell.opportunity_count,
                "verified_refill_count": dwell.verified_refill_count,
                "continuity_segment_count": 1,
                "frame_epoch_sample": dwell.frame_epoch_sample,
                "source_observation_id": dwell.source.source_id,
                "source_glrt_margin": dwell.source.margin,
                "source_bound_cfo_hz": dwell.source_bound_cfo_hz,
                "trajectory_id": dwell.trajectory_id,
                "branch_id": dwell.branch_id,
                "trajectory_alias_index": dwell.trajectory_alias_index,
                "trajectory_coefficients_hz": list(dwell.trajectory_coefficients_hz),
            }
            for dwell in dwells
        ],
        "method_summaries": list(summaries),
    }
    summary_path.write_bytes(_json_bytes(summary))
    artifacts = {
        name: {"path": path.name, "sha256": _sha256(path), "bytes": path.stat().st_size}
        for name, path in (
            ("summary", summary_path),
            ("window_fits", csv_path),
            ("frame_inventory", frame_path),
            ("comparison_plot", plot_path),
        )
    }
    manifest = {
        "schema": "org.leo.research.recent-frame-cfo-rate-artifacts/v1",
        "artifacts": artifacts,
    }
    manifest_path.write_bytes(_json_bytes(manifest))
    return summary


def main() -> int:
    arguments = _arguments()
    summary = run(
        bulk_root=arguments.bulk_root,
        inputs_path=arguments.inputs,
        output_root=arguments.output_root,
        maximum_frames=arguments.maximum_frames,
    )
    print(json.dumps(stable_measurement_floats(summary), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
