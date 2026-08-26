#!/usr/bin/env python3
"""Run the frozen multi-radio common-rate development experiment."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass
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
from leo.analysis.research.multi_radio_common_rate import (  # noqa: E402
    CommonRateFit,
    MultiRadioFramePoint,
    RadioRateFit,
    SeparatePathRateFit,
    block_bootstrap_radio_rate_sigma,
    block_bootstrap_rate_sigma,
    common_rate_prediction_metrics,
    fit_common_rate,
    fit_radio_rates,
    fit_separate_path_rates,
    fixed_history_causal_predictions,
    prediction_metrics_from_causal,
    radio_rate_prediction_metrics,
    separate_rate_prediction_metrics,
)
from leo.analysis.research.multi_radio_common_rate_protocol import (  # noqa: E402
    MultiRadioCaptureBinding,
    MultiRadioCommonRateProtocol,
    MultiRadioPathBinding,
    load_multi_radio_common_rate_protocol,
)
from leo.analysis.starlink.local_doppler import stable_measurement_floats  # noqa: E402
from leo.analysis.starlink.templates import (  # noqa: E402
    FRAME_RATE_HZ,
    OFDM_SYMBOL_DURATION_S,
)
from leo.contracts.digests import canonical_digest  # noqa: E402
from leo.contracts.recording import RecordingStreamV1, RecordingStreamV2  # noqa: E402
from leo.contracts.states import StreamState, TimingMethod  # noqa: E402
from leo.storage import PinnedLocalRoot, RecordingStore  # noqa: E402

DEFAULT_BULK_ROOT = Path("/srv/bulk/leo")
DEFAULT_PROTOCOL = Path("config/analysis/multi-radio-common-rate-protocol-v1.json")
DEFAULT_OUTPUT_ROOT = Path("reports/figures/2026_08_25_multi_radio_common_rate")
SYMBOL_ALIAS_SPACING_HZ = 1.0 / OFDM_SYMBOL_DURATION_S
FIXED_500MS_SCOPE = (
    "Locally strict-past within the frozen episode only; noncausal upstream branch, alias, "
    "source-epoch, and frame-lattice selection used both Qin parities"
)
FRAME_CFO_KERNEL = (
    "split-validation estimator: 100 Hz coarse likelihood grid across the +/-2 kHz basin, "
    "5 Hz fine grid within +/-100 Hz of the coarse winner, three-cell quadratic peak "
    "interpolation when interior, then two phase-slope refinements"
)
DIAGNOSTIC_PROFILE_DISPOSITION = (
    "20 Hz likelihood profiles were computed by the wrapper but their values were discarded; "
    "they did not select support or supply any CFO used by these fits"
)
DISPERSION_INTERPRETATION = (
    "Bootstrap sigma is a post-freeze numerical block-bootstrap dispersion summary on this "
    "opened cohort, not a calibrated uncertainty, material variance-reduction, or cross-radio "
    "identifiability claim"
)


@dataclass(frozen=True, slots=True)
class RuntimePath:
    binding: MultiRadioPathBinding
    config: dict[str, Any]
    source_bound_cfo_hz: float
    model_at_source_hz: float
    trajectory_coefficients_hz: tuple[float, float]
    trajectory_reference_time_s: float
    frame_starts: tuple[int, ...]

    def model_cfo_hz(self, local_time_s: float) -> float:
        model = float(
            np.polyval(
                np.asarray(self.trajectory_coefficients_hz, dtype=float),
                local_time_s - self.trajectory_reference_time_s,
            )
        )
        return self.source_bound_cfo_hz + model - self.model_at_source_hz


@dataclass(frozen=True, slots=True)
class CaptureMeasurements:
    binding: MultiRadioCaptureBinding
    path_configs: tuple[dict[str, Any], ...]
    points: tuple[MultiRadioFramePoint, ...]
    frame_rows: tuple[dict[str, Any], ...]
    path_ledgers: tuple[dict[str, Any], ...]
    read_ledgers: tuple[dict[str, Any], ...]


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=DEFAULT_BULK_ROOT)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser.parse_args()


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


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return value


def _bulk_path(bulk_root: Path, logical_uri: str) -> Path:
    if not logical_uri.startswith("bulk://"):
        raise ValueError("frozen product URI is not a bulk URI")
    relative = Path(logical_uri.removeprefix("bulk://"))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("frozen product URI escaped the bulk root")
    path = (bulk_root / relative).resolve(strict=True)
    root = bulk_root.resolve(strict=True)
    if path != root and root not in path.parents:
        raise ValueError("resolved product escaped the bulk root")
    return path


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


def _verify_path_products(
    *,
    bulk_root: Path,
    analysis_manifest: dict[str, Any],
    path_config: dict[str, Any],
) -> dict[str, Path]:
    products = path_config["products"]
    if not isinstance(products, dict):
        raise ValueError("protocol path products must be an object")
    manifest_products = {
        str(item["logical_uri"]): item
        for item in analysis_manifest["products"]
        if isinstance(item, dict) and "logical_uri" in item
    }
    paths = {}
    for name, binding in products.items():
        if not isinstance(binding, dict):
            raise ValueError("protocol product binding must be an object")
        uri = str(binding["logical_uri"])
        expected = str(binding["sha256"])
        manifest_item = manifest_products.get(uri)
        if manifest_item is None or manifest_item.get("status") != "complete":
            raise ValueError("frozen product is absent or incomplete in analysis manifest")
        if manifest_item.get("digest") != expected:
            raise ValueError("analysis manifest product digest drifted")
        product_path = _bulk_path(bulk_root, uri)
        if _sha256(product_path) != expected:
            raise ValueError("frozen product byte digest drifted")
        paths[str(name)] = product_path
    return paths


def _raw_sources(
    scan: dict[str, Any],
) -> dict[str, tuple[dict[str, Any], dict[str, Any], dict[str, Any]]]:
    if scan.get("schema_version") != 3:
        raise ValueError("multi-radio experiment requires pilot-scan V3")
    output = {}
    for detection in scan["detections"]:
        for candidate in detection["candidates"]:
            scores = [score for score in candidate["scores"] if score["method"] == "glrt64"]
            if len(scores) != 1:
                raise ValueError("pilot candidate lacks exactly one GLRT64 score")
            source_id = canonical_digest(
                {
                    "sample_start": int(detection["sample_start"]),
                    "candidate_rank": int(candidate["rank"]),
                    "method": "glrt64",
                }
            )
            output[source_id] = (detection, candidate, scores[0])
    return output


def _runtime_path(
    *,
    binding: MultiRadioPathBinding,
    path_config: dict[str, Any],
    product_paths: dict[str, Path],
    sample_rate_hz: int,
) -> RuntimePath:
    final = _load(product_paths["final_trajectory_bank"])
    dealiased = _load(product_paths["dealiased_trajectory_bank"])
    scan = _load(product_paths["pilot_scan"])
    trajectories = [
        item
        for item in final["trajectories"]
        if item["trajectory_id"] == binding.trajectory_id
        and item["branch_id"] == binding.branch_id
        and int(item["alias_index"]) == binding.trajectory_alias_index
    ]
    if len(trajectories) != 1:
        raise ValueError("frozen final trajectory is absent or duplicated")
    trajectory = trajectories[0]
    if trajectory["trajectory_id"] not in final["automatic_correction_trajectory_ids"]:
        raise ValueError("frozen final trajectory lost automatic eligibility")
    expected_coefficients = tuple(
        float(value) for value in path_config["trajectory_absolute_coefficients_hz"]
    )
    actual_coefficients = tuple(float(value) for value in trajectory["absolute_coefficients_hz"])
    if actual_coefficients != expected_coefficients or len(actual_coefficients) != 2:
        raise ValueError("frozen trajectory coefficients drifted")
    if float(trajectory["reference_time_s"]) != float(path_config["trajectory_reference_time_s"]):
        raise ValueError("frozen trajectory reference time drifted")
    branches = [item for item in dealiased["branches"] if item["branch_id"] == binding.branch_id]
    if len(branches) != 1:
        raise ValueError("frozen dealiased branch is absent or duplicated")
    branch = branches[0]
    if set(branch["model"]["observation_ids"]) != set(trajectory["observation_ids"]):
        raise ValueError("final and dealiased branch membership disagree")
    source_config = path_config["frozen_source"]
    if not isinstance(source_config, dict):
        raise ValueError("frozen source must be an object")
    source_id = str(source_config["source_observation_id"])
    sources = _raw_sources(scan)
    source = sources.get(source_id)
    if source is None:
        raise ValueError("frozen GLRT64 source is absent")
    detection, candidate, score = source
    source_observations = [
        observation
        for observation in dealiased["observations"]
        if observation["observation_id"] in set(branch["model"]["observation_ids"])
        and observation["source_observation_ids"] == [source_id]
    ]
    if len(source_observations) != 1:
        raise ValueError("frozen source is absent or duplicated in dealiased branch")
    observation = source_observations[0]
    expected_values = (
        int(source_config["sample_start"]),
        float(source_config["detection_time_s"]),
        int(source_config["candidate_rank"]),
        int(source_config["local_epoch_sample"]),
        int(source_config["source_alias_index"]),
        float(source_config["tracking_cfo_hz"]),
        float(source_config["exact_score"]),
        float(source_config["control_score"]),
        float(source_config["margin"]),
    )
    actual_values = (
        int(detection["sample_start"]),
        float(detection["time_s"]),
        int(candidate["rank"]),
        int(candidate["local_epoch_sample"]),
        int(observation["alias_index"]),
        float(score["tracking_cfo_hz"]),
        float(score["exact_score"]),
        float(score["control_score"]),
        float(score["margin"]),
    )
    if actual_values != expected_values:
        raise ValueError("frozen GLRT64 source values drifted")
    source_bound = float(
        score["tracking_cfo_hz"]
        + (binding.trajectory_alias_index - int(observation["alias_index"]))
        * SYMBOL_ALIAS_SPACING_HZ
    )
    reference = float(trajectory["reference_time_s"])
    model_at_source = float(np.polyval(actual_coefficients, float(detection["time_s"]) - reference))
    if abs(source_bound - model_at_source) > 2_000.0:
        raise ValueError("frozen source leaves the final-trajectory CFO basin")
    frame_content = round(302 * sample_rate_hz * OFDM_SYMBOL_DURATION_S)
    starts = _frame_starts(
        int(detection["sample_start"]) + int(candidate["local_epoch_sample"]),
        sample_rate_hz,
        binding.analysis_start_s,
        binding.analysis_stop_s,
        frame_content,
    )
    if len(starts) < 1_000:
        raise ValueError("frozen 1.5 s episode has too few frame opportunities")
    return RuntimePath(
        binding=binding,
        config=path_config,
        source_bound_cfo_hz=source_bound,
        model_at_source_hz=model_at_source,
        trajectory_coefficients_hz=(actual_coefficients[0], actual_coefficients[1]),
        trajectory_reference_time_s=reference,
        frame_starts=starts,
    )


def _complex_receiver(values: np.ndarray, receiver_column: int) -> np.ndarray:
    if values.ndim != 3 or values.shape[2] != 2:
        raise ValueError("CI16 data must have sample, receiver, component axes")
    return np.asarray(
        (
            values[:, receiver_column, 0].astype(float)
            + 1j * values[:, receiver_column, 1].astype(float)
        )
        / (2**15),
        dtype=np.complex128,
    )


def _capture_configs(
    protocol: MultiRadioCommonRateProtocol,
    session_id: str,
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    captures = protocol.document["captures"]
    if not isinstance(captures, list):
        raise ValueError("protocol captures must be an array")
    matches = [item for item in captures if item.get("capture_session_id") == session_id]
    if len(matches) != 1 or not isinstance(matches[0], dict):
        raise ValueError("protocol capture config is absent or duplicated")
    capture_config = matches[0]
    values = capture_config["paths"]
    if not isinstance(values, list) or any(not isinstance(item, dict) for item in values):
        raise ValueError("protocol path configs must be an object array")
    return capture_config, tuple(values)


def _measure_capture(
    *,
    store: RecordingStore,
    bulk_root: Path,
    protocol: MultiRadioCommonRateProtocol,
    capture: MultiRadioCaptureBinding,
) -> CaptureMeasurements:
    capture_config, path_configs = _capture_configs(protocol, capture.session_id)
    path_config_by_id = {str(item["path_id"]): item for item in path_configs}
    if len(path_config_by_id) != len(path_configs):
        raise ValueError("protocol path config contains a duplicate")
    bundle = store.inspect(capture.session_id)
    if bundle.manifest_sha256 != capture.recording_manifest_sha256:
        raise ValueError("recording manifest digest drifted")
    analysis_path = _bulk_path(bulk_root, str(capture_config["analysis_manifest_logical_uri"]))
    if _sha256(analysis_path) != capture.analysis_manifest_sha256:
        raise ValueError("analysis manifest digest drifted")
    analysis_manifest = _load(analysis_path)
    if (
        analysis_manifest.get("session_id") != capture.session_id
        or analysis_manifest.get("run_id") != capture.analysis_run_id
        or analysis_manifest.get("pipeline_lane") != "standard"
    ):
        raise ValueError("analysis manifest identity or lane drifted")
    stream_contracts = {stream.stream_id: stream for stream in bundle.manifest.streams}
    runtimes = []
    for binding in capture.paths:
        config = path_config_by_id[binding.path_id]
        stream = stream_contracts.get(binding.stream_id)
        if not isinstance(stream, RecordingStreamV2):
            raise ValueError("multi-radio experiment requires one V2 stream")
        if stream.radio.radio_id != binding.physical_radio_id or not _continuity_is_lossless(
            stream
        ):
            raise ValueError("stream identity or counter-authoritative continuity drifted")
        if stream.timing is None or (
            stream.timing.first_sample.estimate_utc_ns != binding.first_sample_estimate_utc_ns
        ):
            raise ValueError("first-sample UTC binding drifted")
        settings = stream.applied_settings
        if (
            settings is None
            or settings.sample_rate_hz != 2_500_000
            or settings.center_frequency_hz + 9_750_000_000 != binding.nominal_sky_frequency_hz
            or binding.receiver_id not in settings.receiver_ids
        ):
            raise ValueError("stream tuning or receiver inventory drifted")
        product_paths = _verify_path_products(
            bulk_root=bulk_root,
            analysis_manifest=analysis_manifest,
            path_config=config,
        )
        runtimes.append(
            _runtime_path(
                binding=binding,
                path_config=config,
                product_paths=product_paths,
                sample_rate_hz=settings.sample_rate_hz,
            )
        )

    measurement_config = protocol.document["measurement"]
    coordinate_config = protocol.document["frequency_coordinate"]
    if not isinstance(measurement_config, dict) or not isinstance(coordinate_config, dict):
        raise ValueError("protocol measurement or frequency config is invalid")
    grid = np.arange(
        -float(measurement_config["profile_residual_half_width_hz"]),
        float(measurement_config["profile_residual_half_width_hz"])
        + 0.5 * float(measurement_config["profile_step_hz"]),
        float(measurement_config["profile_step_hz"]),
    )
    frame_config = PilotFrameCfoConfig(
        residual_half_width_hz=float(measurement_config["profile_residual_half_width_hz"]),
        minimum_exact_coherence=float(measurement_config["minimum_even_exact_coherence"]),
        minimum_coherence_margin=float(measurement_config["minimum_even_coherence_margin"]),
    )
    frame_content = round(302 * 2_500_000 * OFDM_SYMBOL_DURATION_S)
    episode_reference_ns = (capture.episode_start_utc_ns + capture.episode_stop_utc_ns) // 2
    points = []
    frame_rows = []
    path_ledgers = []
    read_ledgers = []
    by_stream: dict[str, list[RuntimePath]] = defaultdict(list)
    for runtime in runtimes:
        by_stream[runtime.binding.stream_id].append(runtime)
    for stream_id, stream_runtimes in sorted(by_stream.items()):
        reader = store.reader(bundle, stream_id, verify=True)
        if reader.sample_rate_hz != 2_500_000:
            raise ValueError("reader sample rate drifted")
        gap_map = reader.gap_map()
        if gap_map.segment_count != 1 or gap_map.missing_sample_count != 0:
            raise ValueError("verified gap map is not one lossless segment")
        read_start = min(runtime.frame_starts[0] for runtime in stream_runtimes) - 1
        read_stop = max(runtime.frame_starts[-1] for runtime in stream_runtimes) + frame_content + 1
        receiver_ids = tuple(sorted({runtime.binding.receiver_id for runtime in stream_runtimes}))
        device = reader.read_device_span(
            read_start,
            read_stop - read_start,
            receiver_ids=receiver_ids,
        )
        read_ledgers.append(
            {
                "stream_id": stream_id,
                "physical_radio_id": stream_runtimes[0].binding.physical_radio_id,
                "receiver_ids": list(receiver_ids),
                "device_sample_start": read_start,
                "sample_count": read_stop - read_start,
                "valid_sample_count": int(np.count_nonzero(device.valid_samples)),
                "continuity_segment_ids": sorted(
                    int(value) for value in set(device.continuity_segment_ids.tolist())
                ),
                "reader_verify": True,
                "gap_map_sha256": _v2_stream(stream_contracts, stream_id).gap_map_sha256,
                "timeline_sha256": _v2_stream(stream_contracts, stream_id).timeline_sha256,
            }
        )
        receiver_column = {receiver_id: index for index, receiver_id in enumerate(receiver_ids)}
        for runtime in sorted(stream_runtimes, key=lambda item: item.binding.path_id):
            binding = runtime.binding
            samples = _complex_receiver(device.samples, receiver_column[binding.receiver_id])
            scale = float(coordinate_config["shared_rate_reference_sky_frequency_hz"]) / float(
                binding.nominal_sky_frequency_hz
            )
            supported = 0
            odd_available = 0
            rejection_counts: dict[str, int] = defaultdict(int)
            for frame_index, frame_start in enumerate(runtime.frame_starts):
                local = frame_start - read_start
                selected = slice(local - 1, local + frame_content + 1)
                valid = device.valid_samples[selected]
                segments = device.continuity_segment_ids[selected]
                continuity_safe = bool(np.all(valid) and len(set(segments.tolist())) == 1)
                local_reference_time_s = (frame_start + 1672.0) / reader.sample_rate_hz
                acquisition_cfo = runtime.model_cfo_hz(local_reference_time_s)
                if not continuity_safe:
                    rejection_counts["device_gap_or_segment_crossing"] += 1
                    frame_rows.append(
                        {
                            "capture_session_id": capture.session_id,
                            "path_id": binding.path_id,
                            "frame_index": frame_index,
                            "frame_start_sample": frame_start,
                            "reference_utc_ns": None,
                            "episode_time_s": None,
                            "continuity_safe": False,
                            "training_supported": False,
                            "training_rejection_reasons": ["device_gap_or_segment_crossing"],
                            "even_absolute_cfo_hz": None,
                            "odd_absolute_cfo_hz": None,
                            "normalized_even_cfo_hz": None,
                            "normalized_odd_cfo_hz": None,
                        }
                    )
                    continue
                result = evaluate_edge_pilot_frame_cfo_likelihood(
                    samples[selected],
                    reader.sample_rate_hz,
                    frame_start_sample=frame_start,
                    acquisition_absolute_cfo_hz=acquisition_cfo,
                    edge=binding.edge,
                    residual_grid_hz=grid,
                    config=frame_config,
                )
                split = result.split_validation
                for reason in split.training_rejection_reasons:
                    rejection_counts[str(reason)] += 1
                reference_utc_ns = binding.first_sample_estimate_utc_ns + round(
                    split.reference_sample / reader.sample_rate_hz * 1e9
                )
                episode_time_s = (reference_utc_ns - episode_reference_ns) / 1e9
                even = split.even_absolute_cfo_hz
                odd = split.odd_absolute_cfo_hz
                normalized_even = float(even) * scale if even is not None else None
                normalized_odd = float(odd) * scale if odd is not None else None
                point_id = canonical_digest(
                    {
                        "capture_session_id": capture.session_id,
                        "path_id": binding.path_id,
                        "frame_start_sample": frame_start,
                    }
                )
                frame_rows.append(
                    {
                        "capture_session_id": capture.session_id,
                        "path_id": binding.path_id,
                        "frame_index": frame_index,
                        "frame_start_sample": frame_start,
                        "reference_utc_ns": reference_utc_ns,
                        "episode_time_s": episode_time_s,
                        "continuity_safe": True,
                        "training_supported": split.training_supported,
                        "training_rejection_reasons": list(split.training_rejection_reasons),
                        "acquisition_model_cfo_hz": acquisition_cfo,
                        "even_absolute_cfo_hz": even,
                        "odd_absolute_cfo_hz": odd,
                        "normalized_even_cfo_hz": normalized_even,
                        "normalized_odd_cfo_hz": normalized_odd,
                        "normalization_scale": scale,
                        "even_frequency_uncertainty_hz": split.even_frequency_uncertainty_hz,
                        "even_exact_coherence": split.even_exact_coherence,
                        "even_control_coherence": split.even_control_coherence,
                        "even_coherence_margin": split.even_coherence_margin,
                        "even_search_boundary": split.even_search_boundary,
                        "odd_search_boundary": split.odd_search_boundary,
                        "point_id": point_id,
                    }
                )
                if not split.training_supported or normalized_even is None:
                    continue
                supported += 1
                if normalized_odd is not None:
                    odd_available += 1
                points.append(
                    MultiRadioFramePoint(
                        point_id=point_id,
                        path_id=binding.path_id,
                        physical_radio_id=binding.physical_radio_id,
                        time_s=episode_time_s,
                        even_cfo_hz=normalized_even,
                        odd_cfo_hz=normalized_odd,
                        even_sigma_hz=(
                            float(split.even_frequency_uncertainty_hz) * scale
                            if split.even_frequency_uncertainty_hz is not None
                            else None
                        ),
                    )
                )
            path_ledgers.append(
                {
                    "path_id": binding.path_id,
                    "physical_radio_id": binding.physical_radio_id,
                    "edge": binding.edge,
                    "nominal_sky_frequency_hz": binding.nominal_sky_frequency_hz,
                    "normalization_scale": scale,
                    "opportunity_count": len(runtime.frame_starts),
                    "training_supported_count": supported,
                    "odd_response_available_count_on_supported_mask": odd_available,
                    "training_retention": supported / len(runtime.frame_starts),
                    "training_rejection_counts": dict(sorted(rejection_counts.items())),
                    "branch_id": binding.branch_id,
                    "trajectory_id": binding.trajectory_id,
                    "trajectory_alias_index": binding.trajectory_alias_index,
                    "source_observation_id": binding.source_observation_id,
                    "source_bound_cfo_hz": runtime.source_bound_cfo_hz,
                    "product_digests": dict(binding.product_digests),
                }
            )
    return CaptureMeasurements(
        binding=capture,
        path_configs=path_configs,
        points=tuple(points),
        frame_rows=tuple(frame_rows),
        path_ledgers=tuple(sorted(path_ledgers, key=lambda item: str(item["path_id"]))),
        read_ledgers=tuple(read_ledgers),
    )


def _v2_stream(streams: dict[str, RecordingStreamV1], stream_id: str) -> RecordingStreamV2:
    stream = streams[stream_id]
    if not isinstance(stream, RecordingStreamV2):
        raise ValueError("runtime path refers to a non-V2 stream")
    return stream


def _path_prediction_metrics(
    shared: CommonRateFit,
    radio: tuple[RadioRateFit, ...],
    separate: tuple[SeparatePathRateFit, ...],
    heldout: tuple[MultiRadioFramePoint, ...],
) -> tuple[dict[str, Any], ...]:
    output = []
    for path_id in sorted({point.path_id for point in heldout}):
        selected = tuple(point for point in heldout if point.path_id == path_id)
        shared_metrics = common_rate_prediction_metrics(shared, selected)
        radio_metrics = radio_rate_prediction_metrics(radio, selected)
        separate_metrics = separate_rate_prediction_metrics(separate, selected)
        output.append(
            {
                "path_id": path_id,
                "point_count": len(selected),
                "shared": asdict(shared_metrics),
                "radio": asdict(radio_metrics),
                "separate": asdict(separate_metrics),
            }
        )
    return tuple(output)


def _path_support_ledger_entry(
    *,
    path_id: str,
    physical_radio_id: str,
    values: tuple[MultiRadioFramePoint, ...],
    split_time_s: float,
    minimum_train: int,
    minimum_heldout: int,
) -> dict[str, Any]:
    """Count path membership from even-selected frames, never odd availability."""

    train_count = sum(point.time_s < split_time_s for point in values)
    heldout_selected = tuple(point for point in values if point.time_s >= split_time_s)
    heldout_response_count = sum(point.odd_cfo_hz is not None for point in heldout_selected)
    eligible = train_count >= minimum_train and len(heldout_selected) >= minimum_heldout
    if train_count < minimum_train:
        reason = "insufficient frozen even-Qin training support"
    elif len(heldout_selected) < minimum_heldout:
        reason = "insufficient frozen late even-selected membership support"
    else:
        reason = "even-selected membership support thresholds passed"
    return {
        "path_id": path_id,
        "physical_radio_id": physical_radio_id,
        "train_even_count": train_count,
        "heldout_even_selected_count": len(heldout_selected),
        "heldout_odd_response_available_count": heldout_response_count,
        "heldout_odd_response_missing_count": len(heldout_selected) - heldout_response_count,
        # Retained for V1 evidence readers; this is a response count, not membership.
        "heldout_odd_count_on_even_selected_mask": heldout_response_count,
        "eligible": eligible,
        "reason": reason,
    }


def _heldout_response_failures(
    points: tuple[MultiRadioFramePoint, ...], split_time_s: float
) -> tuple[dict[str, Any], ...]:
    """Retain late even-selected points whose odd-Qin response is unavailable."""

    return tuple(
        {
            "point_id": point.point_id,
            "path_id": point.path_id,
            "physical_radio_id": point.physical_radio_id,
            "time_s": point.time_s,
            "reason": "odd_qin_response_missing_on_even_selected_frame",
        }
        for point in points
        if point.time_s >= split_time_s and point.odd_cfo_hz is None
    )


def _evaluate_capture(
    measurements: CaptureMeasurements,
    *,
    protocol: MultiRadioCommonRateProtocol,
    capture_index: int,
) -> dict[str, Any]:
    evaluation = protocol.document["evaluation"]
    models = protocol.document["models"]
    if not isinstance(evaluation, dict) or not isinstance(models, dict):
        raise ValueError("protocol evaluation or model config is invalid")
    split_time_s = -0.75 + 1.5 * float(evaluation["chronological_train_fraction"])
    minimum_train = int(evaluation["minimum_train_frames_per_path"])
    minimum_heldout = int(evaluation["minimum_heldout_frames_per_path"])
    all_by_path: dict[str, list[MultiRadioFramePoint]] = defaultdict(list)
    for point in measurements.points:
        all_by_path[point.path_id].append(point)
    eligible_paths = []
    support_ledger = []
    for path in measurements.binding.paths:
        values = tuple(all_by_path.get(path.path_id, ()))
        support = _path_support_ledger_entry(
            path_id=path.path_id,
            physical_radio_id=path.physical_radio_id,
            values=values,
            split_time_s=split_time_s,
            minimum_train=minimum_train,
            minimum_heldout=minimum_heldout,
        )
        if support["eligible"]:
            eligible_paths.append(path.path_id)
        support_ledger.append(support)
    eligible_radios = {
        point.physical_radio_id
        for point in measurements.points
        if point.path_id in set(eligible_paths)
    }
    response_failures = _heldout_response_failures(measurements.points, split_time_s)
    if len(eligible_radios) < int(evaluation["minimum_distinct_physical_radios"]):
        return {
            "capture_session_id": measurements.binding.session_id,
            "status": "non_evaluable",
            "reason": "fewer than two physical radios retain frozen support",
            "support_ledger": support_ledger,
            "heldout_response_failures": list(response_failures),
            "path_ledgers": list(measurements.path_ledgers),
            "read_ledgers": list(measurements.read_ledgers),
        }
    eligible_set = set(eligible_paths)
    all_points = tuple(point for point in measurements.points if point.path_id in eligible_set)
    train = tuple(point for point in all_points if point.time_s < split_time_s)
    heldout = tuple(
        point
        for point in all_points
        if point.time_s >= split_time_s and point.odd_cfo_hz is not None
    )
    if not heldout:
        return {
            "capture_session_id": measurements.binding.session_id,
            "status": "non_evaluable",
            "reason": "no held-out odd-Qin responses remain on the even-selected membership",
            "support_ledger": support_ledger,
            "heldout_response_failures": list(response_failures),
            "path_ledgers": list(measurements.path_ledgers),
            "read_ledgers": list(measurements.read_ledgers),
        }
    shared = fit_common_rate(train)
    radio = fit_radio_rates(train)
    separate = fit_separate_path_rates(train)
    shared_metrics = common_rate_prediction_metrics(shared, heldout)
    radio_metrics = radio_rate_prediction_metrics(radio, heldout)
    separate_metrics = separate_rate_prediction_metrics(separate, heldout)
    uncertainty_text = str(evaluation["uncertainty"])
    if "50 ms" not in uncertainty_text or "500" not in uncertainty_text:
        raise ValueError("unsupported frozen uncertainty configuration")
    base_seed = 418_050 + 10_000 * capture_index
    shared_sigma = block_bootstrap_rate_sigma(train, shared=True, seed=base_seed)
    radio_sigma = {
        fit.physical_radio_id: block_bootstrap_radio_rate_sigma(
            tuple(point for point in train if point.physical_radio_id == fit.physical_radio_id),
            seed=base_seed + 100 + index,
        )
        for index, fit in enumerate(radio)
    }
    separate_sigma = {
        fit.path_id: block_bootstrap_rate_sigma(
            tuple(point for point in train if point.path_id == fit.path_id),
            shared=False,
            seed=base_seed + index + 1,
        )
        for index, fit in enumerate(separate)
    }
    causal_config = models["causal_500ms_comparator"]
    if not isinstance(causal_config, dict):
        raise ValueError("causal comparator config is invalid")
    causal = fixed_history_causal_predictions(
        all_points,
        heldout,
        history_s=float(causal_config["history_s"]),
        minimum_history_frames=int(causal_config["minimum_history_frames"]),
    )
    causal_metrics = prediction_metrics_from_causal(causal) if causal else None
    causal_ids = {item.point_id for item in causal}
    causal_mask = tuple(point for point in heldout if point.point_id in causal_ids)
    shared_on_causal = common_rate_prediction_metrics(shared, causal_mask) if causal_mask else None
    radio_on_causal = radio_rate_prediction_metrics(radio, causal_mask) if causal_mask else None
    separate_on_causal = (
        separate_rate_prediction_metrics(separate, causal_mask) if causal_mask else None
    )
    separate_by_path = {fit.path_id: fit for fit in separate}
    radio_by_id = {fit.physical_radio_id: fit for fit in radio}
    causal_by_id = {item.point_id: item for item in causal}
    prediction_rows = []
    for point in heldout:
        path_fit = separate_by_path[point.path_id]
        radio_fit = radio_by_id[point.physical_radio_id]
        causal_item = causal_by_id.get(point.point_id)
        prediction_rows.append(
            {
                "point_id": point.point_id,
                "path_id": point.path_id,
                "time_s": point.time_s,
                "odd_cfo_hz": point.odd_cfo_hz,
                "shared_prediction_hz": shared.predict(point.path_id, point.time_s),
                "radio_prediction_hz": radio_fit.predict(point.path_id, point.time_s),
                "separate_prediction_hz": path_fit.predict(point.time_s),
                "causal_500ms_prediction_hz": (
                    causal_item.prediction_hz if causal_item is not None else None
                ),
                "causal_history_count": (
                    causal_item.history_count if causal_item is not None else None
                ),
            }
        )
    rates = np.asarray([fit.rate_hz_s for fit in separate], dtype=float)
    radio_rates = np.asarray([fit.rate_hz_s for fit in radio], dtype=float)
    common_path_reference = float(np.mean(rates))
    return {
        "capture_session_id": measurements.binding.session_id,
        "status": "evaluable",
        "reason": "two-radio support and frozen train/heldout minima passed",
        "episode_start_utc_ns": measurements.binding.episode_start_utc_ns,
        "episode_stop_utc_ns": measurements.binding.episode_stop_utc_ns,
        "split_episode_time_s": split_time_s,
        "eligible_path_ids": eligible_paths,
        "eligible_physical_radio_ids": sorted(eligible_radios),
        "support_ledger": support_ledger,
        "heldout_response_failures": list(response_failures),
        "path_ledgers": list(measurements.path_ledgers),
        "read_ledgers": list(measurements.read_ledgers),
        "shared_fit": asdict(shared),
        "shared_block_bootstrap_rate_sigma_hz_s": shared_sigma,
        "radio_fits": [
            {
                **asdict(fit),
                "block_bootstrap_rate_sigma_hz_s": radio_sigma[fit.physical_radio_id],
            }
            for fit in radio
        ],
        "separate_fits": [
            {
                **asdict(fit),
                "block_bootstrap_rate_sigma_hz_s": separate_sigma[fit.path_id],
            }
            for fit in separate
        ],
        "path_rate_max_pairwise_disagreement_hz_s": float(np.ptp(rates)),
        "path_rate_rms_about_path_mean_hz_s": float(
            np.sqrt(np.mean((rates - common_path_reference) ** 2))
        ),
        "radio_rate_pairwise_disagreement_hz_s": float(np.ptp(radio_rates)),
        "heldout_metrics": {
            "shared": asdict(shared_metrics),
            "radio": asdict(radio_metrics),
            "separate": asdict(separate_metrics),
            "shared_to_radio_rms_ratio": shared_metrics.rms_hz / radio_metrics.rms_hz,
            "shared_to_separate_rms_ratio": shared_metrics.rms_hz / separate_metrics.rms_hz,
            "by_path": list(_path_prediction_metrics(shared, radio, separate, heldout)),
        },
        "causal_500ms_common_mask_metrics": {
            "target_count": len(causal),
            "causal_500ms": asdict(causal_metrics) if causal_metrics is not None else None,
            "shared": asdict(shared_on_causal) if shared_on_causal is not None else None,
            "radio": asdict(radio_on_causal) if radio_on_causal is not None else None,
            "separate": asdict(separate_on_causal) if separate_on_causal is not None else None,
        },
        "prediction_rows": prediction_rows,
    }


def _sharing_classification(results: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    evaluable = [item for item in results if item["status"] == "evaluable"]
    if not evaluable:
        return {
            "classification": "not_evaluable",
            "reason": "no capture passed the frozen evaluability gates",
        }
    shared_rms = np.asarray(
        [float(item["heldout_metrics"]["shared"]["rms_hz"]) for item in evaluable]
    )
    separate_rms = np.asarray(
        [float(item["heldout_metrics"]["separate"]["rms_hz"]) for item in evaluable]
    )
    capture_ratios = shared_rms / separate_rms
    pooled_shared = float(np.sqrt(np.mean(shared_rms**2)))
    pooled_separate = float(np.sqrt(np.mean(separate_rms**2)))
    prediction_ratio = pooled_shared / pooled_separate
    shared_sigmas = np.asarray(
        [float(item["shared_block_bootstrap_rate_sigma_hz_s"]) for item in evaluable]
    )
    individual_sigmas = np.asarray(
        [
            float(fit["block_bootstrap_rate_sigma_hz_s"])
            for item in evaluable
            for fit in item["separate_fits"]
        ]
    )
    uncertainty_ratio = float(np.median(shared_sigmas) / np.median(individual_sigmas))
    if prediction_ratio < 1.0 and uncertainty_ratio < 1.0 and np.max(capture_ratios) <= 1.10:
        classification = "favorable"
    elif prediction_ratio >= 1.0 and uncertainty_ratio >= 1.0:
        classification = "adverse"
    else:
        classification = "mixed"
    return {
        "classification": classification,
        "evaluable_capture_count": len(evaluable),
        "equal_capture_pooled_shared_heldout_rms_hz": pooled_shared,
        "equal_capture_pooled_separate_heldout_rms_hz": pooled_separate,
        "pooled_shared_to_separate_rms_ratio": prediction_ratio,
        "median_shared_bootstrap_sigma_hz_s": float(np.median(shared_sigmas)),
        "median_individual_bootstrap_sigma_hz_s": float(np.median(individual_sigmas)),
        "shared_to_individual_uncertainty_ratio": uncertainty_ratio,
        "maximum_capture_shared_to_separate_rms_ratio": float(np.max(capture_ratios)),
        "capture_shared_to_separate_rms_ratios": {
            str(item["capture_session_id"]): float(ratio)
            for item, ratio in zip(evaluable, capture_ratios, strict=True)
        },
    }


def _radio_comparator_summary(results: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    """Summarize the task-mandated physical-radio comparator without reclassification."""

    evaluable = [item for item in results if item["status"] == "evaluable"]
    if not evaluable:
        return {"status": "not_evaluable"}
    shared_rms = np.asarray(
        [float(item["heldout_metrics"]["shared"]["rms_hz"]) for item in evaluable]
    )
    radio_rms = np.asarray(
        [float(item["heldout_metrics"]["radio"]["rms_hz"]) for item in evaluable]
    )
    shared_sigma = np.asarray(
        [float(item["shared_block_bootstrap_rate_sigma_hz_s"]) for item in evaluable]
    )
    radio_sigma = np.asarray(
        [
            float(fit["block_bootstrap_rate_sigma_hz_s"])
            for item in evaluable
            for fit in item["radio_fits"]
        ]
    )
    return {
        "status": "post_freeze_protocol_correction_diagnostic",
        "reason": (
            "The parent task mandated separate physical-radio slopes; the response-blind "
            "protocol mistakenly named separate path slopes. Masks and settings are unchanged."
        ),
        "equal_capture_pooled_shared_heldout_rms_hz": float(np.sqrt(np.mean(shared_rms**2))),
        "equal_capture_pooled_radio_heldout_rms_hz": float(np.sqrt(np.mean(radio_rms**2))),
        "pooled_shared_to_radio_rms_ratio": float(
            np.sqrt(np.mean(shared_rms**2)) / np.sqrt(np.mean(radio_rms**2))
        ),
        "median_shared_bootstrap_sigma_hz_s": float(np.median(shared_sigma)),
        "median_radio_bootstrap_sigma_hz_s": float(np.median(radio_sigma)),
        "shared_to_radio_uncertainty_ratio": float(
            np.median(shared_sigma) / np.median(radio_sigma)
        ),
        "capture_shared_to_radio_rms_ratios": {
            str(item["capture_session_id"]): float(ratio)
            for item, ratio in zip(evaluable, shared_rms / radio_rms, strict=True)
        },
    }


def _causal_comparator_summary(results: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    """Pool all models on each capture's identical causal-target mask."""

    evaluable = [
        item
        for item in results
        if item["status"] == "evaluable"
        and item["causal_500ms_common_mask_metrics"]["causal_500ms"] is not None
    ]
    if not evaluable:
        return {"status": "not_evaluable"}

    def pooled(model: str) -> float:
        values = np.asarray(
            [float(item["causal_500ms_common_mask_metrics"][model]["rms_hz"]) for item in evaluable]
        )
        return float(np.sqrt(np.mean(values**2)))

    return {
        "status": "evaluable",
        "evaluable_capture_count": len(evaluable),
        "target_count": sum(
            int(item["causal_500ms_common_mask_metrics"]["target_count"]) for item in evaluable
        ),
        "equal_capture_pooled_rms_hz": {
            model: pooled(model) for model in ("shared", "radio", "separate", "causal_500ms")
        },
    }


def _short_capture(session_id: str) -> str:
    return session_id.split("T", maxsplit=1)[1].split("-", maxsplit=1)[0]


def _path_label(path_id: str) -> str:
    stream, radio, receiver = path_id.split("/")
    return f"{stream}/{radio[-4:]}/{receiver}"


def _odd_response(point: MultiRadioFramePoint) -> float:
    if point.odd_cfo_hz is None:
        raise ValueError("plot point requires an odd-Qin response")
    return point.odd_cfo_hz


def _render_common_tracks(
    path: Path,
    measurements: tuple[CaptureMeasurements, ...],
    results: tuple[dict[str, Any], ...],
) -> None:
    figure = Figure(figsize=(15, 11), constrained_layout=True)
    axes = figure.subplots(2, 2).ravel()
    colors = ("#2563eb", "#ea580c", "#16a34a", "#7c3aed")
    for axis, measured, result in zip(axes, measurements, results, strict=True):
        axis.set_title(
            f"{_short_capture(measured.binding.session_id)} · {result['status']}", loc="left"
        )
        if result["status"] != "evaluable":
            axis.text(0.5, 0.5, str(result["reason"]), ha="center", va="center")
            continue
        shared = result["shared_fit"]
        intercepts = dict(shared["path_intercepts_hz"])
        eligible = set(result["eligible_path_ids"])
        split = float(result["split_episode_time_s"])
        for color, path_id in zip(colors, sorted(eligible), strict=False):
            values = sorted(
                [point for point in measured.points if point.path_id == path_id],
                key=lambda point: point.time_s,
            )
            train = [point for point in values if point.time_s < split]
            heldout = [
                point for point in values if point.time_s >= split and point.odd_cfo_hz is not None
            ]
            offset = float(intercepts[path_id])
            axis.scatter(
                [point.time_s for point in train],
                [point.even_cfo_hz - offset for point in train],
                s=5,
                alpha=0.25,
                color=color,
                rasterized=True,
                label=f"{_path_label(path_id)} even train",
            )
            axis.scatter(
                [point.time_s for point in heldout],
                [_odd_response(point) - offset for point in heldout],
                s=7,
                alpha=0.35,
                marker="x",
                color=color,
                rasterized=True,
                label=f"{_path_label(path_id)} odd heldout",
            )
        times = np.linspace(-0.75, 0.75, 300)
        shared_line = float(shared["rate_hz_s"]) * (times - float(shared["reference_time_s"]))
        axis.plot(times, shared_line, color="#111827", linewidth=2.2, label="shared rate")
        axis.axvline(split, color="#111827", linestyle="--", linewidth=1)
        axis.grid(alpha=0.22)
        axis.set_xlabel("Time from episode midpoint (s)")
        axis.set_ylabel("Path-centered normalized CFO (Hz at 11 GHz)")
        axis.legend(fontsize=6, ncol=2)
    figure.suptitle(
        "Two-radio frame-CFO episodes: one shared normalized rate with free path offsets",
        fontsize=15,
    )
    figure.supxlabel(
        "Dots fit even Qin in the first 60%; crosses are fit-withheld odd Qin in the final 40%. "
        "Upstream branch/alias/frame acquisition used both parities.",
        fontsize=8,
    )
    figure.savefig(path, dpi=180, metadata={"Software": "leo-tracker"})


def _render_summary(path: Path, results: tuple[dict[str, Any], ...]) -> None:
    evaluable = [item for item in results if item["status"] == "evaluable"]
    figure = Figure(figsize=(14, 9), constrained_layout=True)
    axes = figure.subplots(2, 1)
    axis = axes[0]
    x = np.arange(len(evaluable), dtype=float)
    for capture_index, item in enumerate(evaluable):
        shared = item["shared_fit"]
        axis.errorbar(
            capture_index,
            float(shared["rate_hz_s"]) / 1_000.0,
            yerr=float(item["shared_block_bootstrap_rate_sigma_hz_s"]) / 1_000.0,
            fmt="o",
            color="#111827",
            capsize=4,
            markersize=7,
            label="shared" if capture_index == 0 else None,
        )
        fits = item["radio_fits"]
        offsets = np.linspace(-0.18, 0.18, len(fits))
        for index, (offset, fit) in enumerate(zip(offsets, fits, strict=True)):
            axis.errorbar(
                capture_index + offset,
                float(fit["rate_hz_s"]) / 1_000.0,
                yerr=float(fit["block_bootstrap_rate_sigma_hz_s"]) / 1_000.0,
                fmt="s",
                color=("#2563eb", "#16a34a")[index],
                alpha=0.75,
                capsize=2,
                markersize=4,
                label=(
                    "radio "
                    f"{str(fit['physical_radio_id']).rsplit('_', maxsplit=1)[-1]} "
                    "(post-freeze diagnostic)"
                    if capture_index == 0
                    else None
                ),
            )
    axis.set_xticks(x, [_short_capture(str(item["capture_session_id"])) for item in evaluable])
    axis.set_ylabel("Normalized CFO rate (kHz/s at 11 GHz)")
    axis.set_title(
        "A  Shared rates and post-freeze physical-radio diagnostic · 50 ms block σ",
        loc="left",
    )
    axis.grid(alpha=0.25)
    axis.legend(fontsize=8, ncol=5)

    axis = axes[1]
    width = 0.19
    shared_rms = [float(item["heldout_metrics"]["shared"]["rms_hz"]) for item in evaluable]
    radio_rms = [float(item["heldout_metrics"]["radio"]["rms_hz"]) for item in evaluable]
    separate_rms = [float(item["heldout_metrics"]["separate"]["rms_hz"]) for item in evaluable]
    causal_rms = [
        float(item["causal_500ms_common_mask_metrics"]["causal_500ms"]["rms_hz"])
        for item in evaluable
    ]
    axis.bar(x - 1.5 * width, shared_rms, width, color="#111827", label="shared episode line")
    axis.bar(
        x - 0.5 * width,
        radio_rms,
        width,
        color="#16a34a",
        label="physical-radio lines (post-freeze diagnostic)",
    )
    axis.bar(
        x + 0.5 * width,
        separate_rms,
        width,
        color="#2563eb",
        label="separate receiver-path lines",
    )
    axis.bar(
        x + 1.5 * width,
        causal_rms,
        width,
        color="#ea580c",
        label="500 ms locally past-only*",
    )
    axis.set_xticks(x, [_short_capture(str(item["capture_session_id"])) for item in evaluable])
    axis.set_ylabel("Held-out odd-Qin CFO RMS (Hz at 11 GHz)")
    axis.set_title("B  Prediction on frozen even-selected response masks", loc="left")
    axis.grid(alpha=0.25, axis="y")
    axis.legend(fontsize=8)
    figure.suptitle("Shared-rate prediction and post-freeze physical-radio diagnostic", fontsize=15)
    figure.supxlabel(
        "* Strictly earlier even Qin inside the episode; upstream branch/alias/frame selection "
        "used both Qin parities.",
        fontsize=8,
    )
    figure.savefig(path, dpi=180, metadata={"Software": "leo-tracker"})


def _render_residuals(path: Path, results: tuple[dict[str, Any], ...]) -> None:
    figure = Figure(figsize=(15, 11), constrained_layout=True)
    axes = figure.subplots(2, 2).ravel()
    for axis, result in zip(axes, results, strict=True):
        axis.set_title(
            f"{_short_capture(str(result['capture_session_id']))} · held-out residual", loc="left"
        )
        if result["status"] != "evaluable":
            axis.text(0.5, 0.5, str(result["reason"]), ha="center", va="center")
            continue
        rows = result["prediction_rows"]
        times = np.asarray([float(item["time_s"]) for item in rows])
        odd = np.asarray([float(item["odd_cfo_hz"]) for item in rows])
        shared = odd - np.asarray([float(item["shared_prediction_hz"]) for item in rows])
        radio = odd - np.asarray([float(item["radio_prediction_hz"]) for item in rows])
        separate = odd - np.asarray([float(item["separate_prediction_hz"]) for item in rows])
        axis.scatter(times, shared, s=6, alpha=0.25, color="#111827", label="shared")
        axis.scatter(
            times,
            radio,
            s=6,
            alpha=0.25,
            color="#16a34a",
            label="radio (post-freeze diagnostic)",
        )
        axis.scatter(times, separate, s=6, alpha=0.25, color="#2563eb", label="separate")
        causal_rows = [item for item in rows if item["causal_500ms_prediction_hz"] is not None]
        axis.scatter(
            [float(item["time_s"]) for item in causal_rows],
            [
                float(item["odd_cfo_hz"]) - float(item["causal_500ms_prediction_hz"])
                for item in causal_rows
            ],
            s=7,
            alpha=0.32,
            color="#ea580c",
            label="500 ms locally past-only*",
        )
        axis.axhline(0.0, color="#64748b", linewidth=1)
        axis.grid(alpha=0.22)
        axis.set_xlabel("Time from episode midpoint (s)")
        axis.set_ylabel("Odd-Qin prediction error (Hz at 11 GHz)")
        axis.legend(fontsize=8)
    figure.suptitle(
        "Held-out odd-Qin residuals · physical-radio curve is a post-freeze diagnostic",
        fontsize=15,
    )
    figure.supxlabel(
        "* Strictly earlier even Qin inside the episode; upstream branch/alias/frame selection "
        "used both Qin parities.",
        fontsize=8,
    )
    figure.savefig(path, dpi=180, metadata={"Software": "leo-tracker"})


def _write_frame_rows(path: Path, measurements: tuple[CaptureMeasurements, ...]) -> None:
    with (
        path.open("wb") as raw_destination,
        gzip.GzipFile(filename="", fileobj=raw_destination, mode="wb", mtime=0) as compressed,
        io.TextIOWrapper(compressed, encoding="utf-8", newline="") as destination,
    ):
        for measured in measurements:
            for row in measured.frame_rows:
                destination.write(
                    json.dumps(
                        stable_measurement_floats(row),
                        allow_nan=False,
                        sort_keys=True,
                    )
                    + "\n"
                )


def _write_csv(path: Path, results: tuple[dict[str, Any], ...]) -> None:
    fields = (
        "capture_session_id",
        "status",
        "path_id",
        "physical_radio_id",
        "shared_rate_hz_s",
        "shared_rate_sigma_hz_s",
        "radio_rate_hz_s",
        "radio_rate_sigma_hz_s",
        "path_rate_hz_s",
        "path_rate_sigma_hz_s",
        "radio_minus_shared_rate_hz_s",
        "path_minus_shared_rate_hz_s",
        "radio_pairwise_disagreement_hz_s",
        "path_max_pairwise_disagreement_hz_s",
        "shared_heldout_rms_hz",
        "radio_heldout_rms_hz",
        "path_heldout_rms_hz",
        "causal_500ms_heldout_rms_hz",
    )
    rows: list[dict[str, Any]] = []
    for item in results:
        if item["status"] != "evaluable":
            row = dict.fromkeys(fields, "")
            row.update(
                capture_session_id=item["capture_session_id"],
                status=item["status"],
            )
            rows.append(row)
            continue
        shared_rate = float(item["shared_fit"]["rate_hz_s"])
        radio_by_id = {fit["physical_radio_id"]: fit for fit in item["radio_fits"]}
        for fit in item["separate_fits"]:
            radio_fit = radio_by_id[fit["physical_radio_id"]]
            rows.append(
                {
                    "capture_session_id": item["capture_session_id"],
                    "status": item["status"],
                    "path_id": fit["path_id"],
                    "physical_radio_id": fit["physical_radio_id"],
                    "shared_rate_hz_s": shared_rate,
                    "shared_rate_sigma_hz_s": item["shared_block_bootstrap_rate_sigma_hz_s"],
                    "radio_rate_hz_s": radio_fit["rate_hz_s"],
                    "radio_rate_sigma_hz_s": radio_fit["block_bootstrap_rate_sigma_hz_s"],
                    "path_rate_hz_s": fit["rate_hz_s"],
                    "path_rate_sigma_hz_s": fit["block_bootstrap_rate_sigma_hz_s"],
                    "radio_minus_shared_rate_hz_s": (float(radio_fit["rate_hz_s"]) - shared_rate),
                    "path_minus_shared_rate_hz_s": float(fit["rate_hz_s"]) - shared_rate,
                    "radio_pairwise_disagreement_hz_s": item[
                        "radio_rate_pairwise_disagreement_hz_s"
                    ],
                    "path_max_pairwise_disagreement_hz_s": item[
                        "path_rate_max_pairwise_disagreement_hz_s"
                    ],
                    "shared_heldout_rms_hz": item["heldout_metrics"]["shared"]["rms_hz"],
                    "radio_heldout_rms_hz": item["heldout_metrics"]["radio"]["rms_hz"],
                    "path_heldout_rms_hz": item["heldout_metrics"]["separate"]["rms_hz"],
                    "causal_500ms_heldout_rms_hz": item["causal_500ms_common_mask_metrics"][
                        "causal_500ms"
                    ]["rms_hz"],
                }
            )
    with path.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def run(*, bulk_root: Path, protocol_path: Path, output_root: Path) -> dict[str, Any]:
    repository_root = Path(__file__).parents[1]
    protocol = load_multi_radio_common_rate_protocol(
        protocol_path,
        repository_root=repository_root,
    )
    output_root.mkdir(parents=True, exist_ok=True)
    store = RecordingStore.open_pinned(PinnedLocalRoot(bulk_root))
    try:
        measurements = tuple(
            _measure_capture(
                store=store,
                bulk_root=bulk_root,
                protocol=protocol,
                capture=capture,
            )
            for capture in protocol.captures
        )
    finally:
        store.close()
    results = tuple(
        _evaluate_capture(measured, protocol=protocol, capture_index=index)
        for index, measured in enumerate(measurements)
    )
    if tuple(item["capture_session_id"] for item in results) != tuple(
        capture.session_id for capture in protocol.captures
    ):
        raise ValueError("result ledger does not retain the complete frozen cohort")
    classification = _sharing_classification(results)
    radio_comparator = _radio_comparator_summary(results)
    causal_comparator = _causal_comparator_summary(results)

    evidence_path = output_root / "multi-radio-common-rate-evidence.json"
    frame_path = output_root / "frame-measurements.jsonl.gz"
    csv_path = output_root / "rate-summary.csv"
    tracks_path = output_root / "common-rate-fits.png"
    summary_path = output_root / "rate-and-prediction-summary.png"
    residual_path = output_root / "heldout-residuals.png"
    manifest_path = output_root / "artifact-manifest.json"
    _write_frame_rows(frame_path, measurements)
    _write_csv(csv_path, results)
    _render_common_tracks(tracks_path, measurements, results)
    _render_summary(summary_path, results)
    _render_residuals(residual_path, results)
    evidence: dict[str, Any] = {
        "schema": "org.leo.research.multi-radio-common-rate-evidence/v1",
        "candidate_only": True,
        "known_pilots_only": True,
        "carrier_phase_connected": False,
        "physical_doppler_truth_available": False,
        "data_phase": "POST-FIX counter-authoritative continuous recording",
        "protocol": {
            "path": str(protocol_path),
            "sha256": protocol.sha256,
            "basis_commit": protocol.document["authority"]["protocol_basis_repository_commit"],
            "protocol_freeze_commit": "a7cc5e755b236c30347aa0765db0a2ade3df27a1",
        },
        "leakage_boundary": {
            "local_fit_symbols": "even Qin only",
            "local_response_symbols": "odd Qin only; fit-withheld from every new model",
            "upstream_conditioning": (
                "Standard GLRT64 branch, alias, source epoch, and frame lattice used even and odd "
                "Qin before this experiment"
            ),
            "fixed_500ms_scope": FIXED_500MS_SCOPE,
            "path_membership": (
                "Late membership counts even-selected frames without testing odd-response "
                "availability; missing odd responses remain explicit response failures"
            ),
        },
        "measurement_kernel": {
            "reported_frame_cfo": FRAME_CFO_KERNEL,
            "diagnostic_profiles": DIAGNOSTIC_PROFILE_DISPOSITION,
        },
        "dispersion_interpretation": DISPERSION_INTERPRETATION,
        "publication_audit": {
            "status": "wording_labels_and_eligibility_seam_corrected_after_audit",
            "frozen_numeric_results_changed": False,
            "frozen_response_masks_changed": False,
            "physical_radio_comparator_label": "post-freeze diagnostic",
        },
        "protocol_correction": {
            "status": "disclosed_post_freeze_task_mandate_correction",
            "frozen_protocol_comparator": "one independent slope per receiver path",
            "parent_task_mandated_comparator": (
                "one independent slope per physical radio with free receiver-path intercepts"
            ),
            "handling": (
                "Both are reported on unchanged frozen masks. The preregistered favorable/mixed/"
                "adverse classification remains based only on the frozen path comparator; the "
                "radio comparator is descriptive and cannot revise that classification."
            ),
        },
        "frequency_authority": {
            "coordinate": "normalized to nominal 11 GHz",
            "lnb_lo_hz": 9_750_000_000,
            "calibrated": False,
            "clock_drift_removed": False,
        },
        "implementation_sha256": {
            "tool": _sha256(Path(__file__)),
            "model": _sha256(
                repository_root / "src/leo/analysis/research/multi_radio_common_rate.py"
            ),
            "protocol_loader": _sha256(
                repository_root / "src/leo/analysis/research/multi_radio_common_rate_protocol.py"
            ),
            "frame_estimator": _sha256(repository_root / "src/leo/analysis/qam/pilot.py"),
        },
        "capture_results": list(results),
        "aggregate": {
            "frozen_path_comparator_classification": classification,
            "task_mandated_radio_comparator": radio_comparator,
            "fixed_500ms_common_mask_comparison": causal_comparator,
        },
    }
    evidence_path.write_bytes(_json_bytes(evidence))
    artifacts = {
        name: {"path": path.name, "sha256": _sha256(path), "bytes": path.stat().st_size}
        for name, path in (
            ("evidence", evidence_path),
            ("frame_measurements", frame_path),
            ("rate_summary_csv", csv_path),
            ("common_rate_fits_png", tracks_path),
            ("rate_prediction_summary_png", summary_path),
            ("heldout_residuals_png", residual_path),
        )
    }
    manifest = {
        "schema": "org.leo.research.multi-radio-common-rate-artifact-manifest/v1",
        "protocol_sha256": protocol.sha256,
        "artifacts": artifacts,
    }
    manifest_path.write_bytes(_json_bytes(manifest))
    return evidence


def main() -> None:
    arguments = _arguments()
    evidence = run(
        bulk_root=arguments.bulk_root,
        protocol_path=arguments.protocol,
        output_root=arguments.output_root,
    )
    print(json.dumps(evidence["aggregate"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
