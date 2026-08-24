#!/usr/bin/env python3
"""Reproduce the CH2L frame-CFO and Kalman-rate diagnosis from immutable IQ."""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import math
from dataclasses import asdict
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
import zstandard as zstd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from leo.analysis.qam.pilot import analyze_pilot_phase_slope  # noqa: E402
from leo.analysis.qam.pilot_pnt_kalman import (  # noqa: E402
    PilotPntKalmanConfig,
    analyze_contiguous_pilot_pnt_kalman,
)
from leo.analysis.starlink.local_doppler import (  # noqa: E402
    frequency_line,
    interleaved_held_out_rms,
    line_slope_sigma,
    stable_measurement_floats,
)
from leo.analysis.starlink.templates import StarlinkEdge  # noqa: E402
from leo.scanner.analysis_models import (  # noqa: E402
    ScannerAnalysisBundleManifestV4,
    ScannerAnalysisMetricsV2,
    ScannerPilotDopplerConfigV1,
    ScannerPilotDopplerSegmentsV1,
    ScannerPilotDopplerSegmentV1,
)
from leo.scanner.models import ScannerIqBundleManifestV2  # noqa: E402

TOOL_VERSION = "scan-ch2l-kalman-rate-diagnosis-v1"
EXPECTED_SCAN_ID = "scan-burst-2b2a98cc0de846b8-03"
EXPECTED_TARGET_INDEX = 2
DEFAULT_OUTPUT_ROOT = Path("reports/figures/2026_08_24_scan_2b2a98cc_ch2l_kalman_rate_diagnosis")
DEFAULT_RECEIPT_NAME = "diagnostic-metrics.json"
DEFAULT_FIGURE_NAME = "ch2l-cfo-kalman-comparison.png"

INK = "#17354a"
BLUE = "#2f83b7"
GREEN = "#2a9d8f"
AMBER = "#d9881f"
GRAY = "#8b98a5"
LIGHT_BLUE = "#d9edf7"


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _without_prefix(value: str) -> str:
    return value.removeprefix("sha256:")


def _read_json_model(path: Path, model_type):
    payload = path.read_bytes()
    return model_type.model_validate_json(payload), payload


def _read_iq(path: Path, manifest: ScannerIqBundleManifestV2) -> np.ndarray:
    if path.stat().st_size != manifest.compressed_bytes:
        raise ValueError("compressed IQ length disagrees with the recording manifest")
    if _sha256_file(path) != _without_prefix(str(manifest.compressed_sha256)):
        raise ValueError("compressed IQ digest disagrees with the recording manifest")
    with (
        path.open("rb") as compressed,
        zstd.ZstdDecompressor().stream_reader(compressed) as reader,
    ):
        raw = reader.read(manifest.uncompressed_bytes + 1)
    if len(raw) != manifest.uncompressed_bytes:
        raise ValueError("uncompressed IQ length disagrees with the recording manifest")
    if _sha256_bytes(raw) != _without_prefix(str(manifest.uncompressed_sha256)):
        raise ValueError("uncompressed IQ digest disagrees with the recording manifest")
    receiver_count = len(manifest.configuration.receiver_ids)
    return np.frombuffer(raw, dtype="<i2").reshape(
        manifest.total_sample_count,
        receiver_count,
        2,
    )


def variant_configs(config: ScannerPilotDopplerConfigV1) -> dict[str, PilotPntKalmanConfig]:
    """Return the exact four matched Kalman configurations used by this report."""

    common = {
        "timing_innovation_gate_sigma": config.timing_innovation_gate_sigma,
    }
    return {
        "default_full": PilotPntKalmanConfig(
            phase_innovation_gate_rad=config.phase_innovation_gate_rad,
            **common,
        ),
        "phase_disabled_after_initialization": PilotPntKalmanConfig(
            phase_innovation_gate_rad=1e-12,
            **common,
        ),
        "phase_sigma_fixed_0p5_rad": PilotPntKalmanConfig(
            phase_innovation_gate_rad=config.phase_innovation_gate_rad,
            minimum_phase_measurement_sigma_rad=0.5,
            maximum_phase_measurement_sigma_rad=0.5,
            **common,
        ),
        "bootstrap_disabled": PilotPntKalmanConfig(
            phase_innovation_gate_rad=config.phase_innovation_gate_rad,
            rate_bootstrap_supported_frames=100,
            **common,
        ),
    }


def _measurement_scales(
    samples: np.ndarray,
    sample_rate_hz: int,
    *,
    epoch_sample: int,
    initial_absolute_cfo_hz: float,
    edge: StarlinkEdge,
    maximum_residual_cfo_hz: float,
    config: PilotPntKalmanConfig,
) -> list[dict[str, float]]:
    """Recreate the per-frame measurement sigmas used inside the tracker."""

    result = analyze_pilot_phase_slope(
        samples,
        sample_rate_hz,
        epoch_sample=epoch_sample,
        absolute_cfo_hz=initial_absolute_cfo_hz,
        edge=edge,
        maximum_residual_cfo_hz=maximum_residual_cfo_hz,
    )
    values: list[dict[str, float]] = []
    for frame in result.frames:
        values.append(
            {
                "phase_measurement_sigma_rad": float(
                    np.clip(
                        frame.phase_residual_rms_rad / math.sqrt(frame.symbol_count),
                        config.minimum_phase_measurement_sigma_rad,
                        config.maximum_phase_measurement_sigma_rad,
                    )
                ),
                "frequency_measurement_sigma_hz": float(
                    max(
                        frame.frequency_uncertainty_hz,
                        config.minimum_frequency_measurement_sigma_hz,
                    )
                ),
            }
        )
    return values


def _quadratic_summary(times_s: np.ndarray, values_hz: np.ndarray) -> dict[str, float]:
    reference_s = float(np.mean(times_s))
    centered = times_s - reference_s
    line_design = np.column_stack((np.ones(times_s.size), centered))
    quad_design = np.column_stack((np.ones(times_s.size), centered, centered**2))
    line_coefficients = np.linalg.lstsq(line_design, values_hz, rcond=None)[0]
    quad_coefficients = np.linalg.lstsq(quad_design, values_hz, rcond=None)[0]
    line_residuals = values_hz - line_design @ line_coefficients
    quad_residuals = values_hz - quad_design @ quad_coefficients
    line_rss = float(np.sum(line_residuals**2))
    quad_rss = float(np.sum(quad_residuals**2))
    degrees_of_freedom = times_s.size - quad_design.shape[1]
    covariance = quad_rss / degrees_of_freedom * np.linalg.inv(quad_design.T @ quad_design)
    endpoint_offset_s = float(times_s[-1] - reference_s)
    endpoint_jacobian = np.asarray((0.0, 1.0, 2.0 * endpoint_offset_s))
    endpoint_rate_hz_s = float(
        quad_coefficients[1] + 2.0 * quad_coefficients[2] * endpoint_offset_s
    )
    endpoint_rate_sigma_hz_s = float(
        math.sqrt(max(float(endpoint_jacobian @ covariance @ endpoint_jacobian), 0.0))
    )
    acceleration_hz_s2 = float(2.0 * quad_coefficients[2])
    acceleration_sigma_hz_s2 = float(math.sqrt(max(4.0 * covariance[2, 2], 0.0)))
    count = times_s.size
    line_aic = count * math.log(line_rss / count) + 2.0 * 2
    quad_aic = count * math.log(quad_rss / count) + 2.0 * 3
    line_bic = count * math.log(line_rss / count) + math.log(count) * 2
    quad_bic = count * math.log(quad_rss / count) + math.log(count) * 3
    return {
        "reference_time_s": reference_s,
        "endpoint_rate_hz_s": endpoint_rate_hz_s,
        "endpoint_rate_sigma_hz_s": endpoint_rate_sigma_hz_s,
        "acceleration_hz_s2": acceleration_hz_s2,
        "acceleration_sigma_hz_s2": acceleration_sigma_hz_s2,
        "aic_delta_vs_line": float(quad_aic - line_aic),
        "bic_delta_vs_line": float(quad_bic - line_bic),
    }


def _glrt_windows(
    metrics: ScannerAnalysisMetricsV2,
    segment: ScannerPilotDopplerSegmentV1,
) -> list[dict[str, Any]]:
    """Return every fully contained rank-0 20 ms GLRT window for the receiver."""

    frame = next(item for item in metrics.frames if item.target_index == segment.target_index)
    bound_roles = {
        (segment.source_probe_index, segment.source_candidate_rank): "source",
        (segment.confirmation_probe_index, segment.confirmation_candidate_rank): "confirmation",
    }
    start_limit_ms = segment.window_start_s * 1000.0
    end_limit_ms = segment.window_end_s * 1000.0
    result = []
    for probe in sorted(frame.probes, key=lambda item: item.probe_index):
        probe_end_ms = probe.probe_start_ms + metrics.configuration.probe_ms
        if (
            probe.receiver_id != segment.receiver_id
            or probe.probe_start_ms < start_limit_ms - 1e-9
            or probe_end_ms > end_limit_ms + 1e-9
        ):
            continue
        candidate = next(
            (item for item in probe.candidates if item.candidate_rank == 0),
            None,
        )
        if candidate is None:
            raise ValueError("fully contained GLRT probe has no rank-0 candidate")
        binding = bound_roles.get((probe.probe_index, candidate.candidate_rank))
        result.append(
            {
                "segment_binding": binding,
                "probe_index": probe.probe_index,
                "probe_start_ms": probe.probe_start_ms,
                "probe_end_ms": probe_end_ms,
                "candidate_rank": candidate.candidate_rank,
                "epoch_sample": candidate.epoch_sample,
                "tracking_cfo_hz": candidate.tracking_cfo_hz,
                "exact_score": candidate.exact_score,
                "control_score": candidate.control_score,
                "margin": candidate.margin,
                "passed_margin_gate": candidate.passed_margin_gate,
            }
        )
    bindings = [item["segment_binding"] for item in result if item["segment_binding"] is not None]
    if bindings != ["source", "confirmation"]:
        raise ValueError("fully contained GLRT windows do not preserve segment bindings")
    return result


def _source_hashes() -> dict[str, str]:
    symbols = {
        "src/leo/analysis/qam/pilot_pnt_kalman.py": analyze_contiguous_pilot_pnt_kalman,
        "src/leo/analysis/qam/pilot.py": analyze_pilot_phase_slope,
        "src/leo/analysis/starlink/local_doppler.py": frequency_line,
    }
    result = {}
    for relative_path, symbol in symbols.items():
        source = inspect.getsourcefile(symbol)
        if source is None:
            raise ValueError(f"cannot resolve source file for {symbol}")
        result[relative_path] = _sha256_file(Path(source))
    scanner_source = Path(__file__).resolve().parents[1] / "src/leo/scanner/pilot_doppler.py"
    result["src/leo/scanner/pilot_doppler.py"] = _sha256_file(scanner_source)
    return result


def _receiver_receipt(
    frame_ci16: np.ndarray,
    receiver_index: int,
    sample_rate_hz: int,
    segment: ScannerPilotDopplerSegmentV1,
    metrics: ScannerAnalysisMetricsV2,
    product: ScannerPilotDopplerSegmentsV1,
) -> dict[str, Any]:
    start_sample = round(segment.window_start_s * sample_rate_hz)
    stop_sample = round(segment.window_end_s * sample_rate_hz)
    ci16 = frame_ci16[start_sample:stop_sample, receiver_index]
    samples = (ci16[:, 0].astype(np.float64) + 1j * ci16[:, 1].astype(np.float64)) / 32768.0
    configs = variant_configs(product.config)
    results = {
        name: analyze_contiguous_pilot_pnt_kalman(
            np.ascontiguousarray(samples),
            sample_rate_hz,
            epoch_sample=segment.source_epoch_sample,
            initial_absolute_cfo_hz=segment.initial_tracking_cfo_hz,
            edge=segment.target.edge,
            maximum_residual_cfo_hz=product.config.maximum_residual_cfo_hz,
            config=config,
        )
        for name, config in configs.items()
    }
    default = results["default_full"]
    phase_disabled = results["phase_disabled_after_initialization"]
    if len(default.frames) != len(phase_disabled.frames):
        raise ValueError("matched variants returned different frame counts")
    default_measurements = np.asarray(
        [item.absolute_cfo_measurement_hz for item in default.frames],
        dtype=float,
    )
    for name, result in results.items():
        measurements = np.asarray(
            [item.absolute_cfo_measurement_hz for item in result.frames],
            dtype=float,
        )
        if not np.array_equal(default_measurements, measurements):
            raise ValueError(f"variant {name} changed the independent frame-CFO vector")
    if len(default.frames) != len(segment.frames):
        raise ValueError("replay frame count disagrees with the persisted segment")
    for replay_frame, persisted_frame in zip(default.frames, segment.frames, strict=True):
        replay_time_s = segment.window_start_s + replay_frame.time_s
        if not math.isclose(
            replay_time_s,
            persisted_frame.time_since_retune_s,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("replay frame time disagrees with the persisted product")
        if not math.isclose(
            replay_frame.absolute_cfo_measurement_hz,
            persisted_frame.absolute_cfo_measurement_hz,
            rel_tol=0.0,
            abs_tol=1e-5,
        ):
            raise ValueError("replay frame CFO disagrees with the persisted product")
    default_final = default.frames[-1]
    if segment.kalman_doppler_rate_hz_s is None or not math.isclose(
        default_final.tracked_doppler_rate_hz_s,
        segment.kalman_doppler_rate_hz_s,
        rel_tol=0.0,
        abs_tol=1e-5,
    ):
        raise ValueError("default replay final rate disagrees with the persisted product")

    scales = _measurement_scales(
        samples,
        sample_rate_hz,
        epoch_sample=segment.source_epoch_sample,
        initial_absolute_cfo_hz=segment.initial_tracking_cfo_hz,
        edge=StarlinkEdge(segment.target.edge),
        maximum_residual_cfo_hz=product.config.maximum_residual_cfo_hz,
        config=configs["default_full"],
    )
    if len(scales) != len(default.frames):
        raise ValueError("measurement-scale inventory disagrees with tracker frames")

    supported_indexes = [
        index for index, item in enumerate(default.frames) if item.measurement_supported
    ]
    times_s = np.asarray(
        [segment.window_start_s + default.frames[index].time_s for index in supported_indexes],
        dtype=float,
    )
    frequencies_hz = default_measurements[supported_indexes]
    direct = frequency_line(times_s, frequencies_hz)
    if direct is None:
        raise ValueError("supported frame CFOs did not produce a direct line")
    direct_sigma = line_slope_sigma(times_s, direct)
    if direct_sigma is None:
        raise ValueError("supported frame CFOs did not produce a slope sigma")
    if segment.local_doppler_rate_hz_s is None or not math.isclose(
        direct.slope_hz_per_s,
        segment.local_doppler_rate_hz_s,
        rel_tol=0.0,
        abs_tol=1e-5,
    ):
        raise ValueError("direct replay rate disagrees with the persisted product")
    direct_prediction = direct.intercept_at_reference_hz + direct.slope_hz_per_s * (
        times_s - direct.reference_time_s
    )
    direct_residuals_hz = frequencies_hz - direct_prediction

    frames = []
    for default_frame, phase_disabled_frame, scale in zip(
        default.frames, phase_disabled.frames, scales, strict=True
    ):
        frames.append(
            {
                "frame_index": default_frame.frame_index,
                "time_since_retune_s": segment.window_start_s + default_frame.time_s,
                "measurement_supported": default_frame.measurement_supported,
                "absolute_cfo_measurement_hz": default_frame.absolute_cfo_measurement_hz,
                "frequency_measurement_sigma_hz": scale["frequency_measurement_sigma_hz"],
                "phase_measurement_sigma_rad": scale["phase_measurement_sigma_rad"],
                "phase_innovation_modulo_pi_rad": (default_frame.phase_innovation_modulo_pi_rad),
                "frequency_innovation_pre_update_hz": default_frame.frequency_innovation_hz,
                "default_tracked_cfo_post_update_hz": default_frame.tracked_absolute_cfo_hz,
                "default_tracked_rate_post_update_hz_s": (default_frame.tracked_doppler_rate_hz_s),
                "default_cfo_measurement_minus_post_update_hz": (
                    default_frame.absolute_cfo_measurement_hz
                    - default_frame.tracked_absolute_cfo_hz
                ),
                "default_cfo_posterior_sigma_hz": default_frame.frequency_sigma_hz,
                "default_rate_posterior_sigma_hz_s": (default_frame.doppler_rate_sigma_hz_s),
                "default_phase_update_applied": default_frame.phase_update_applied,
                "default_frequency_update_applied": default_frame.frequency_update_applied,
                "default_timing_update_applied": default_frame.timing_update_applied,
                "default_rate_bootstrapped": default_frame.doppler_rate_bootstrapped,
                "phase_disabled_tracked_cfo_post_update_hz": (
                    phase_disabled_frame.tracked_absolute_cfo_hz
                ),
                "phase_disabled_tracked_rate_post_update_hz_s": (
                    phase_disabled_frame.tracked_doppler_rate_hz_s
                ),
                "phase_disabled_cfo_measurement_minus_post_update_hz": (
                    phase_disabled_frame.absolute_cfo_measurement_hz
                    - phase_disabled_frame.tracked_absolute_cfo_hz
                ),
                "phase_disabled_phase_update_applied": (phase_disabled_frame.phase_update_applied),
            }
        )

    frequency_innovations_hz = np.asarray(
        [item.frequency_innovation_hz for item in default.frames], dtype=float
    )
    phase_innovations_rad = np.asarray(
        [item.phase_innovation_modulo_pi_rad for item in default.frames], dtype=float
    )
    phase_measurement_sigmas_rad = np.asarray(
        [item["phase_measurement_sigma_rad"] for item in scales], dtype=float
    )
    default_post_update_residuals_hz = np.asarray(
        [
            item.absolute_cfo_measurement_hz - item.tracked_absolute_cfo_hz
            for item in default.frames
        ],
        dtype=float,
    )
    phase_disabled_post_update_residuals_hz = np.asarray(
        [
            item.absolute_cfo_measurement_hz - item.tracked_absolute_cfo_hz
            for item in phase_disabled.frames
        ],
        dtype=float,
    )
    frequency_measurement_sigmas_hz = np.asarray(
        [item["frequency_measurement_sigma_hz"] for item in scales], dtype=float
    )

    variants = {}
    for name, result in results.items():
        final = result.frames[-1]
        variants[name] = {
            "config": asdict(configs[name]),
            "rate_bootstrap_frame_index": result.rate_bootstrap_frame_index,
            "phase_update_count": result.phase_update_count,
            "frequency_update_count": result.frequency_update_count,
            "timing_update_count": result.timing_update_count,
            "final_rate_hz_s": final.tracked_doppler_rate_hz_s,
            "final_rate_posterior_sigma_hz_s": final.doppler_rate_sigma_hz_s,
            "final_cfo_hz": final.tracked_absolute_cfo_hz,
            "final_cfo_posterior_sigma_hz": final.frequency_sigma_hz,
        }

    glrt_windows = _glrt_windows(metrics, segment)

    return {
        "receiver_id": segment.receiver_id,
        "segment_id": str(segment.segment_id),
        "initial_tracking_cfo_hz": segment.initial_tracking_cfo_hz,
        "glrt_windows": glrt_windows,
        "glrt_anchors": [item for item in glrt_windows if item["segment_binding"] is not None],
        "frames": frames,
        "direct": {
            "supported_frame_count": len(supported_indexes),
            "reference_time_s": direct.reference_time_s,
            "cfo_at_reference_hz": direct.intercept_at_reference_hz,
            "rate_hz_s": direct.slope_hz_per_s,
            "conditional_rate_sigma_hz_s": direct_sigma,
            "line_rms_hz": direct.residual_rms_hz,
            "interleaved_held_out_rms_hz": interleaved_held_out_rms(times_s, frequencies_hz),
            "pearson_cfo_time": float(np.corrcoef(times_s, frequencies_hz)[0, 1]),
            "first_to_last_cfo_change_hz": float(frequencies_hz[-1] - frequencies_hz[0]),
            "endpoint_slope_hz_s": float(
                (frequencies_hz[-1] - frequencies_hz[0]) / (times_s[-1] - times_s[0])
            ),
            "median_frequency_measurement_sigma_hz": float(
                np.median(frequency_measurement_sigmas_hz[supported_indexes])
            ),
            "expected_adjacent_change_hz": float(
                direct.slope_hz_per_s * np.median(np.diff(times_s))
            ),
            "adjacent_difference_rate_sd_hz_s": float(
                np.std(np.diff(frequencies_hz) / np.diff(times_s), ddof=1)
            ),
            "residuals_hz": direct_residuals_hz.tolist(),
        },
        "diagnostics": {
            "frequency_innovation_definition": (
                "frame CFO measurement minus causal pre-update predicted CFO"
            ),
            "cfo_post_update_residual_definition": (
                "frame CFO measurement minus same-frame post-update tracked CFO"
            ),
            "normalized_phase_innovation_rms_definition": (
                "sqrt(mean((modulo-pi phase innovation / within-frame assigned phase "
                "measurement sigma)^2)) over all returned frames"
            ),
            "full_frequency_innovation_mean_hz": float(np.mean(frequency_innovations_hz)),
            "full_frequency_innovation_rms_hz": float(
                math.sqrt(np.mean(frequency_innovations_hz**2))
            ),
            "full_normalized_phase_innovation_rms": float(
                math.sqrt(np.mean((phase_innovations_rad / phase_measurement_sigmas_rad) ** 2))
            ),
            "full_cfo_post_update_residual_mean_hz": float(
                np.mean(default_post_update_residuals_hz)
            ),
            "full_cfo_post_update_residual_rms_hz": float(
                math.sqrt(np.mean(default_post_update_residuals_hz**2))
            ),
            "phase_disabled_cfo_post_update_residual_mean_hz": float(
                np.mean(phase_disabled_post_update_residuals_hz)
            ),
            "phase_disabled_cfo_post_update_residual_rms_hz": float(
                math.sqrt(np.mean(phase_disabled_post_update_residuals_hz**2))
            ),
        },
        "quadratic_ols": _quadratic_summary(times_s, frequencies_hz),
        "variants": variants,
        "published": {
            "qualified": segment.qualified,
            "qualification_failures": list(segment.qualification_failures),
            "local_minus_kalman_rate_hz_s": segment.local_minus_kalman_rate_hz_s,
        },
    }


def build_receipt(
    recording_dir: Path,
    analysis_dir: Path,
    *,
    analysis_code_revision: str,
    target_index: int = EXPECTED_TARGET_INDEX,
) -> dict[str, Any]:
    """Verify immutable inputs and build the complete report evidence receipt."""

    manifest_path = recording_dir / "manifest.json"
    metrics_path = analysis_dir / "scanner-metrics.v2.json"
    product_path = analysis_dir / "scanner-pilot-doppler-segments.v1.json"
    analysis_manifest_path = analysis_dir / "manifest.json"
    manifest, manifest_payload = _read_json_model(manifest_path, ScannerIqBundleManifestV2)
    metrics, metrics_payload = _read_json_model(metrics_path, ScannerAnalysisMetricsV2)
    product, product_payload = _read_json_model(product_path, ScannerPilotDopplerSegmentsV1)
    analysis_manifest, analysis_manifest_payload = _read_json_model(
        analysis_manifest_path, ScannerAnalysisBundleManifestV4
    )
    manifest_sha256 = _sha256_bytes(manifest_payload)
    metrics_sha256 = _sha256_bytes(metrics_payload)
    product_sha256 = _sha256_bytes(product_payload)
    if _without_prefix(str(metrics.input_manifest_sha256)) != manifest_sha256:
        raise ValueError("scanner metrics input manifest digest disagrees")
    if _without_prefix(str(product.input_manifest_sha256)) != manifest_sha256:
        raise ValueError("pilot product input manifest digest disagrees")
    if _without_prefix(str(product.scanner_metrics_sha256)) != metrics_sha256:
        raise ValueError("pilot product metrics digest disagrees")
    if _without_prefix(str(analysis_manifest.input_manifest_sha256)) != manifest_sha256:
        raise ValueError("analysis manifest input digest disagrees")
    if _without_prefix(str(analysis_manifest.metrics_sha256)) != metrics_sha256:
        raise ValueError("analysis manifest metrics digest disagrees")
    if _without_prefix(str(analysis_manifest.pilot_doppler_sha256)) != product_sha256:
        raise ValueError("analysis manifest pilot-product digest disagrees")
    if not (manifest.scan_id == metrics.scan_id == product.scan_id == analysis_manifest.scan_id):
        raise ValueError("recording and analysis scan identities disagree")
    if len({metrics.input_uri, product.input_uri, analysis_manifest.input_uri}) != 1:
        raise ValueError("recording and analysis input URIs disagree")
    if metrics.configuration != manifest.configuration:
        raise ValueError("recording and analysis scanner configurations disagree")
    if product.source_frame_count != len(metrics.frames):
        raise ValueError("pilot product source-frame inventory disagrees")
    if manifest.scan_id != EXPECTED_SCAN_ID:
        raise ValueError("input is not the scan bound to this focused report")
    if target_index != EXPECTED_TARGET_INDEX:
        raise ValueError("focused report is bound to CH2L target index 2")

    iq = _read_iq(recording_dir / manifest.payload_relative_path, manifest)
    frame = next(item for item in manifest.frames if item.target_index == target_index)
    if frame.target.channel != 2 or StarlinkEdge(frame.target.edge) is not StarlinkEdge.LOWER:
        raise ValueError("target index 2 is not CH2 lower")
    metrics_frame = next(item for item in metrics.frames if item.target_index == target_index)
    if (
        metrics_frame.target != frame.target
        or metrics_frame.source_sample_start != frame.sample_start
        or metrics_frame.sample_count != frame.sample_count
        or metrics_frame.iq_sha256 != frame.uncompressed_sha256
    ):
        raise ValueError("recording and analysis CH2L frame bindings disagree")
    frame_ci16 = iq[frame.sample_start : frame.sample_start + frame.sample_count]
    if _sha256_bytes(frame_ci16.tobytes(order="C")) != _without_prefix(
        str(frame.uncompressed_sha256)
    ):
        raise ValueError("target frame digest disagrees with the recording manifest")
    segments = sorted(
        (item for item in product.segments if item.target_index == target_index),
        key=lambda item: item.receiver_id,
    )
    if len(segments) != 2:
        raise ValueError("diagnosis requires exactly two receiver segments for the target")
    if any(segment.target != frame.target for segment in segments):
        raise ValueError("pilot segments disagree with the CH2L target identity")
    receiver_receipts = []
    for segment in segments:
        try:
            receiver_index = manifest.configuration.receiver_ids.index(segment.receiver_id)
        except ValueError as error:
            raise ValueError(
                "segment receiver is absent from the recording configuration"
            ) from error
        receiver_receipts.append(
            _receiver_receipt(
                frame_ci16,
                receiver_index,
                manifest.configuration.sample_rate_hz,
                segment,
                metrics,
                product,
            )
        )

    left, right = receiver_receipts
    left_frames = left["frames"]
    right_frames = right["frames"]
    left_phase = np.asarray(
        [item["phase_innovation_modulo_pi_rad"] for item in left_frames], dtype=float
    )
    right_phase = np.asarray(
        [item["phase_innovation_modulo_pi_rad"] for item in right_frames], dtype=float
    )
    left_residual = np.asarray(left["direct"]["residuals_hz"], dtype=float)
    right_residual = np.asarray(right["direct"]["residuals_hz"], dtype=float)
    pair = next(item for item in product.receiver_pairs if item.target_index == target_index)

    receipt = {
        "schema_version": 2,
        "kind": "research.scan-ch2l-kalman-rate-diagnosis",
        "tool_version": TOOL_VERSION,
        "classification": "supporting-retrospective",
        "scan_id": manifest.scan_id,
        "analysis_code_revision": analysis_code_revision,
        "generator_sha256": _sha256_file(Path(__file__).resolve()),
        "source_sha256": _source_hashes(),
        "inputs": {
            "recording_uri": product.input_uri,
            "recording_manifest_sha256": manifest_sha256,
            "compressed_iq_sha256": _sha256_file(recording_dir / manifest.payload_relative_path),
            "uncompressed_iq_sha256": _without_prefix(str(manifest.uncompressed_sha256)),
            "target_frame_uncompressed_sha256": _without_prefix(str(frame.uncompressed_sha256)),
            "analysis_id": analysis_manifest.analysis_id,
            "analysis_manifest_sha256": _sha256_bytes(analysis_manifest_payload),
            "scanner_metrics_sha256": metrics_sha256,
            "pilot_doppler_product_sha256": product_sha256,
            "pilot_doppler_content_digest": _without_prefix(str(product.content_digest)),
        },
        "target": {
            "target_index": target_index,
            "channel": frame.target.channel,
            "edge": frame.target.edge,
            "requested_rf_center_hz": frame.target.rf_center_hz,
            "actual_rf_center_hz": frame.actual_rf_center_hz,
            "sample_rate_hz": manifest.configuration.sample_rate_hz,
            "stored_sample_start": frame.sample_start,
            "stored_sample_end_exclusive": frame.sample_start + frame.sample_count,
            "sample_time_realtime_start_ns": frame.sample_time_realtime_start_ns,
            "sample_time_realtime_end_ns": frame.sample_time_realtime_end_ns,
            "sample_time_uncertainty_ns": frame.sample_time_uncertainty_ns,
            "first_sample_sequence": frame.first_sample_sequence,
            "last_sample_sequence_exclusive": frame.last_sample_sequence_exclusive,
            "missing_samples_before": frame.missing_samples_before,
            "overflow_observed": frame.overflow_observed,
            "within_frame_continuity": frame.within_frame_continuity,
        },
        "product_config": product.config.model_dump(mode="json"),
        "receivers": receiver_receipts,
        "cross_receiver": {
            "direct_rate_difference_hz_s": (
                left["direct"]["rate_hz_s"] - right["direct"]["rate_hz_s"]
            ),
            "absolute_cfo_midpoint_difference_hz": abs(
                left["direct"]["cfo_at_reference_hz"] - right["direct"]["cfo_at_reference_hz"]
            ),
            "phase_innovation_correlation": float(np.corrcoef(left_phase, right_phase)[0, 1]),
            "detrended_frame_cfo_residual_correlation": float(
                np.corrcoef(left_residual, right_residual)[0, 1]
            ),
            "receiver_pair_both_qualified": pair.both_qualified,
            "receiver_pair_rate_published": pair.local_rate_difference_hz_s is not None,
        },
        "resource_disclosure": {
            "process_count": 1,
            "wall_time_recorded": False,
            "blas_thread_count_controlled": False,
            "peak_rss_recorded": False,
            "benchmark_claimed": False,
        },
    }
    return stable_measurement_floats(receipt)


def render(receipt: dict[str, Any], output_path: Path) -> None:
    """Render the bound GLRT, frame-CFO, and Kalman comparison."""

    receivers = receipt["receivers"]
    if len(receivers) != 2:
        raise ValueError("figure requires exactly two receiver receipts")
    matplotlib.rcParams.update(
        {
            "font.size": 9.5,
            "axes.titlesize": 11,
            "axes.labelsize": 10,
            "figure.facecolor": "#f7fafc",
            "axes.facecolor": "#ffffff",
        }
    )
    figure, axes = plt.subplots(
        2,
        2,
        figsize=(15.8, 9.4),
        sharex="col",
        sharey="row",
        constrained_layout=False,
    )
    figure.subplots_adjust(
        left=0.065,
        right=0.995,
        top=0.88,
        bottom=0.155,
        hspace=0.035,
        wspace=0.025,
    )
    figure.suptitle(
        f"CH2L · {receipt['scan_id']} · CFO evidence and causal rate state",
        fontsize=15,
        fontweight="bold",
        color=INK,
        y=0.985,
    )
    figure.text(
        0.5,
        0.945,
        "Each receiver is centered by its own 75 ms Huber intercept; "
        "time and row scales are shared",
        ha="center",
        color="#445b6e",
    )
    for column, receiver in enumerate(receivers):
        frames = receiver["frames"]
        times_ms = np.asarray(
            [item["time_since_retune_s"] * 1000.0 for item in frames], dtype=float
        )
        measured_hz = np.asarray(
            [item["absolute_cfo_measurement_hz"] for item in frames], dtype=float
        )
        default_cfo_hz = np.asarray(
            [item["default_tracked_cfo_post_update_hz"] for item in frames], dtype=float
        )
        phase_disabled_cfo_hz = np.asarray(
            [item["phase_disabled_tracked_cfo_post_update_hz"] for item in frames],
            dtype=float,
        )
        default_rate_hz_s = np.asarray(
            [item["default_tracked_rate_post_update_hz_s"] for item in frames], dtype=float
        )
        phase_disabled_rate_hz_s = np.asarray(
            [item["phase_disabled_tracked_rate_post_update_hz_s"] for item in frames],
            dtype=float,
        )
        direct = receiver["direct"]
        reference_hz = direct["cfo_at_reference_hz"]
        direct_line_hz = reference_hz + direct["rate_hz_s"] * (
            times_ms / 1000.0 - direct["reference_time_s"]
        )
        qualification = (
            "published qualified"
            if receiver["published"]["qualified"]
            else "failed direct/Kalman agreement"
        )

        cfo_axis = axes[0, column]
        cfo_axis.scatter(
            times_ms,
            measured_hz - reference_hz,
            s=24,
            facecolors="none",
            edgecolors=BLUE,
            linewidths=1.1,
            label="1.333 ms frame CFO",
            zorder=4,
        )
        cfo_axis.plot(
            times_ms,
            default_cfo_hz - reference_hz,
            color=BLUE,
            linewidth=1.6,
            label="full Kalman CFO",
            zorder=3,
        )
        cfo_axis.plot(
            times_ms,
            phase_disabled_cfo_hz - reference_hz,
            color=GREEN,
            linewidth=1.4,
            label="phase-disabled control CFO",
            zorder=3,
        )
        cfo_axis.plot(
            times_ms,
            direct_line_hz - reference_hz,
            color=INK,
            linestyle="--",
            linewidth=1.8,
            label="75 ms Huber line",
            zorder=2,
        )
        unbound_label_used = False
        bound_label_used = False
        for window in receiver["glrt_windows"]:
            is_bound = window["segment_binding"] is not None
            cfo_axis.plot(
                [window["probe_start_ms"], window["probe_end_ms"]],
                [
                    window["tracking_cfo_hz"] - reference_hz,
                    window["tracking_cfo_hz"] - reference_hz,
                ],
                color=AMBER if is_bound else GRAY,
                linewidth=5.0 if is_bound else 3.0,
                solid_capstyle="butt",
                alpha=0.9 if is_bound else 0.55,
                label=(
                    "segment-bound 20 ms GLRT CFO"
                    if is_bound and not bound_label_used
                    else (
                        "other fully contained rank-0 GLRT CFO"
                        if not is_bound and not unbound_label_used
                        else None
                    )
                ),
                zorder=1,
            )
            bound_label_used = bound_label_used or is_bound
            unbound_label_used = unbound_label_used or not is_bound
        cfo_axis.axhline(0.0, color=GRAY, linewidth=0.7, alpha=0.5)
        cfo_axis.set_title(
            f"RX{receiver['receiver_id']} · {qualification}\nreference CFO {reference_hz:+.3f} Hz",
            loc="left",
            fontweight="bold",
        )
        cfo_axis.grid(alpha=0.20)
        if column == 0:
            cfo_axis.set_ylabel("CFO - RX-specific Huber midpoint (Hz)")

        rate_axis = axes[1, column]
        rate_axis.plot(
            times_ms,
            default_rate_hz_s / 1000.0,
            color=BLUE,
            linewidth=1.7,
            label="full Kalman rate",
        )
        rate_axis.plot(
            times_ms,
            phase_disabled_rate_hz_s / 1000.0,
            color=GREEN,
            linewidth=1.5,
            label="phase-disabled control rate",
        )
        direct_rate = direct["rate_hz_s"] / 1000.0
        direct_sigma = direct["conditional_rate_sigma_hz_s"] / 1000.0
        rate_axis.axhspan(
            direct_rate - direct_sigma,
            direct_rate + direct_sigma,
            color=LIGHT_BLUE,
            alpha=0.55,
            label="direct conditional sigma",
        )
        rate_axis.axhline(
            direct_rate,
            color=INK,
            linestyle="--",
            linewidth=1.8,
            label="75 ms Huber rate",
        )
        bootstrap_index = receiver["variants"]["default_full"]["rate_bootstrap_frame_index"]
        if bootstrap_index is not None:
            rate_axis.axvline(
                times_ms[bootstrap_index],
                color=GRAY,
                linestyle=":",
                linewidth=1.2,
                label="default bootstrap frame",
            )
        rate_axis.scatter(
            [times_ms[-1]],
            [default_rate_hz_s[-1] / 1000.0],
            color=BLUE,
            marker="x",
            s=60,
            zorder=4,
        )
        rate_axis.scatter(
            [times_ms[-1]],
            [phase_disabled_rate_hz_s[-1] / 1000.0],
            color=GREEN,
            marker="x",
            s=60,
            zorder=4,
        )
        rate_axis.text(
            0.02,
            0.04,
            f"direct {direct_rate:+.3f} kHz/s\n"
            f"full final {default_rate_hz_s[-1] / 1000.0:+.3f} kHz/s\n"
            f"phase-disabled {phase_disabled_rate_hz_s[-1] / 1000.0:+.3f} kHz/s",
            transform=rate_axis.transAxes,
            va="bottom",
            color="#334e68",
            bbox={"facecolor": "white", "edgecolor": "#c9d4dd", "alpha": 0.9},
        )
        rate_axis.grid(alpha=0.20)
        rate_axis.set_xlabel("time since CH2L retune (ms)")
        if column == 0:
            rate_axis.set_ylabel("CFO rate (kHz/s)")

    cfo_handles, cfo_labels = axes[0, 0].get_legend_handles_labels()
    rate_handles, rate_labels = axes[1, 0].get_legend_handles_labels()
    figure.legend(
        cfo_handles + rate_handles,
        cfo_labels + rate_labels,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.012),
        ncol=5,
        frameon=False,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(
        output_path,
        dpi=180,
        metadata={"Software": "leo-tracker-reduxredux"},
    )
    plt.close(figure)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recording-dir", type=Path, required=True)
    parser.add_argument("--analysis-dir", type=Path, required=True)
    parser.add_argument("--analysis-code-revision", required=True)
    parser.add_argument("--target-index", type=int, default=2)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser.parse_args()


def main() -> None:
    args = _arguments()
    receipt = build_receipt(
        args.recording_dir,
        args.analysis_dir,
        analysis_code_revision=args.analysis_code_revision,
        target_index=args.target_index,
    )
    args.output_root.mkdir(parents=True, exist_ok=True)
    receipt_path = args.output_root / DEFAULT_RECEIPT_NAME
    figure_path = args.output_root / DEFAULT_FIGURE_NAME
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    render(receipt, figure_path)
    print(receipt_path)
    print(figure_path)


if __name__ == "__main__":
    main()
