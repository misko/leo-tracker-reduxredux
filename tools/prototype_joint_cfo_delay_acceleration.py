#!/usr/bin/env python3
"""Blocked prototype for empirical CFO and quantized frame-delay dynamics.

The two measurements share candidate selection and window lineage, but they
use their own measurement times and are not converted into one another.  The
joint state is block diagonal: a cubic
empirical CFO trajectory and a quadratic template-relative delay trajectory.
The integer GLRT epoch is modeled as an interval-censored observation after an
exact 10,000/3-sample rational frame lattice correction.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

INPUT_ROOT = Path("/tmp/cap-20260825T150802-chunked-full-branch-37p575-51p4-tolerance4-v3")
INPUT_PATH = INPUT_ROOT / "epoch-doppler-curvature.json"
LONG_EVIDENCE_PATH = INPUT_ROOT / "evidence.json"
FRAME_ROWS_PATH = INPUT_ROOT / "frame-rows.jsonl"
OUTPUT_ROOT = Path("/tmp/joint-cfo-delay-acceleration-prototype")

EXPECTED_INPUT_SHA256 = "24bf59d774c2ca20dd896dd090fdafe146abca5218c54f161c1e07c3ac203f7d"
EXPECTED_LONG_EVIDENCE_SHA256 = "619a715143c20801efbe8be3dee012b1a83e3fc730d588bb3a2c6cd2382de579"
EXPECTED_FRAME_ROWS_SHA256 = "2d40f818bb76723629227704066137c0947a9523742f60fdd1cfad3a79842fd4"
EXPECTED_SCHEMA = "org.leo.research.detailed-epoch-doppler-curvature/v1"
EXPECTED_TRAJECTORY_ID = "sha256:92955a7dc86076490a7150b7f233ef64519fb7c0999bba1e62d94dfa531b5d8c"
RF_CENTER_HZ = 11_440_312_500.0

SAMPLE_RATE_HZ = 2_500_000
FRAME_RATE_HZ = 750
FRAME_PERIOD_NUMERATOR = 10_000
FRAME_PERIOD_DENOMINATOR = 3
GLRT_WINDOW_SAMPLE_COUNT = 50_000
GLRT_FIRST_SYMBOL = 2
GLRT_LAST_SYMBOL = 65
OFDM_SYMBOL_DURATION_S = 4.4e-6
REFERENCE_TIME_S = (37.575 + 51.4) / 2.0
PRIMARY_CFO_DEGREE = 3
PRIMARY_DELAY_DEGREE = 2
ROLLING_FIRST_VALIDATION_BLOCK = 43
TIMING_SIGMA_BOUNDS = (0.02, 2.0)


@dataclass(frozen=True, slots=True)
class Cohort:
    probe_time_s: np.ndarray
    epoch_time_s: np.ndarray
    cfo_measurement_time_s: np.ndarray
    cfo_centroid_local_sample: np.ndarray
    cfo_supported_frame_count: np.ndarray
    cfo_hz: np.ndarray
    observed_epoch: np.ndarray
    frame_index: np.ndarray
    nominal_epoch_thirds: np.ndarray
    delay_center_samples: np.ndarray
    delay_lower_samples: np.ndarray
    delay_upper_samples: np.ndarray
    cfo_calendar_block: np.ndarray
    delay_calendar_block: np.ndarray
    exact_score: np.ndarray
    control_score: np.ndarray
    margin: np.ndarray


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def factorial_basis(times_s: np.ndarray, degree: int) -> np.ndarray:
    """Return [1, tau, tau^2/2!, ...] at a frozen time origin."""

    tau = np.asarray(times_s, dtype=float) - REFERENCE_TIME_S
    return np.column_stack(
        [np.power(tau, order) / math.factorial(order) for order in range(degree + 1)]
    )


def rational_lattice(
    absolute_epochs: np.ndarray, reference_epoch: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Resolve fixed frame indexes and exact rational-lattice quantizer cells."""

    delta = np.asarray(absolute_epochs, dtype=np.int64) - int(reference_epoch)
    frame_index = np.rint(delta * FRAME_PERIOD_DENOMINATOR / FRAME_PERIOD_NUMERATOR).astype(
        np.int64
    )
    nominal_thirds = (
        FRAME_PERIOD_DENOMINATOR * int(reference_epoch) + FRAME_PERIOD_NUMERATOR * frame_index
    )
    center = (
        FRAME_PERIOD_DENOMINATOR * np.asarray(absolute_epochs, dtype=np.int64) - nominal_thirds
    ) / FRAME_PERIOD_DENOMINATOR
    lower = center - 0.5
    upper = center + 0.5
    return frame_index, nominal_thirds, center, lower, upper


def quantize_delay(nominal_epoch_thirds: np.ndarray, delay_samples: np.ndarray) -> np.ndarray:
    absolute = nominal_epoch_thirds.astype(float) / FRAME_PERIOD_DENOMINATOR
    quantized: np.ndarray = np.floor(absolute + np.asarray(delay_samples) + 0.5).astype(np.int64)
    return quantized


def glrt64_correlation_centroid_local_sample(
    local_epoch_sample: int,
    *,
    window_sample_count: int = GLRT_WINDOW_SAMPLE_COUNT,
) -> tuple[float, int]:
    """Return the mean local center of the samples supporting one GLRT64 CFO.

    This mirrors the production workspace geometry: rational frame starts are
    rounded independently, symbols 2..65 use rounded symbol boundaries, and
    selection stops before the first frame lacking any selected symbol.
    """

    if local_epoch_sample < 0 or window_sample_count < 1:
        raise ValueError("epoch and window geometry must be nonnegative")
    frame_period = SAMPLE_RATE_HZ / FRAME_RATE_HZ
    symbol_period = SAMPLE_RATE_HZ * OFDM_SYMBOL_DURATION_S
    symbols = np.arange(GLRT_FIRST_SYMBOL, GLRT_LAST_SYMBOL + 1)
    local_starts = np.rint(symbols * symbol_period).astype(np.int64)
    local_stops = np.rint((symbols + 1) * symbol_period).astype(np.int64)
    sample_counts = local_stops - local_starts
    centers: list[float] = []
    frame_count = 0
    while True:
        frame_start = local_epoch_sample + round(frame_count * frame_period)
        if (
            frame_start >= window_sample_count
            or frame_start + int(local_starts[0]) >= window_sample_count
        ):
            break
        starts = frame_start + local_starts
        valid = (starts >= 0) & (starts + sample_counts <= window_sample_count)
        if not bool(np.all(valid)):
            break
        centers.extend((starts + (sample_counts - 1) / 2.0).tolist())
        frame_count += 1
    if not centers:
        raise ValueError("GLRT64 geometry has no complete selected-symbol frame")
    return float(np.mean(centers)), frame_count


def robust_scale(values: np.ndarray) -> float:
    centered = values - float(np.median(values))
    scale = 1.4826 * float(np.median(np.abs(centered)))
    if not math.isfinite(scale) or scale < 1e-9:
        scale = float(np.sqrt(np.mean(np.square(centered))))
    return max(scale, 1e-9)


def fit_huber(
    times_s: np.ndarray,
    values: np.ndarray,
    degree: int,
    *,
    tuning: float = 1.345,
    maximum_iterations: int = 200,
) -> dict[str, Any]:
    design = factorial_basis(times_s, degree)
    coefficients, *_ = np.linalg.lstsq(design, values, rcond=None)
    converged = False
    _iteration = 0
    for _iteration in range(1, maximum_iterations + 1):
        residual = values - design @ coefficients
        scale = robust_scale(residual)
        cutoff = tuning * scale
        weights = np.minimum(1.0, cutoff / np.maximum(np.abs(residual), 1e-12))
        weighted_design = design * np.sqrt(weights)[:, None]
        weighted_values = values * np.sqrt(weights)
        updated, *_ = np.linalg.lstsq(weighted_design, weighted_values, rcond=None)
        if np.max(np.abs(updated - coefficients)) <= 1e-10 * (1.0 + np.max(np.abs(coefficients))):
            coefficients = updated
            converged = True
            break
        coefficients = updated
    residual = values - design @ coefficients
    return {
        "coefficients": coefficients,
        "residual_scale": robust_scale(residual),
        "iterations": _iteration,
        "converged": converged,
    }


def normal_cdf(values: np.ndarray) -> np.ndarray:
    return np.fromiter(
        (0.5 * math.erfc(-float(value) / math.sqrt(2.0)) for value in values),
        dtype=float,
        count=values.size,
    )


def interval_probability(
    standardized_lower: np.ndarray, standardized_upper: np.ndarray
) -> np.ndarray:
    output = np.empty(standardized_lower.shape, dtype=float)
    left = standardized_upper <= 0.0
    right = standardized_lower >= 0.0
    middle = ~(left | right)
    if np.any(left):
        output[left] = normal_cdf(standardized_upper[left]) - normal_cdf(standardized_lower[left])
    if np.any(right):
        output[right] = normal_cdf(-standardized_lower[right]) - normal_cdf(
            -standardized_upper[right]
        )
    if np.any(middle):
        output[middle] = normal_cdf(standardized_upper[middle]) - normal_cdf(
            standardized_lower[middle]
        )
    return np.maximum(output, np.finfo(float).tiny)


def interval_log_probability(
    lower: np.ndarray,
    upper: np.ndarray,
    mean: np.ndarray,
    sigma: float | np.ndarray,
) -> np.ndarray:
    standardized_lower = (lower - mean) / sigma
    standardized_upper = (upper - mean) / sigma
    return np.log(interval_probability(standardized_lower, standardized_upper))


def fit_interval_timing(
    times_s: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
    degree: int,
) -> dict[str, Any]:
    """Fit a Gaussian-before-quantizer regression with deterministic EM."""

    design = factorial_basis(times_s, degree)
    centers = 0.5 * (lower + upper)
    coefficients, *_ = np.linalg.lstsq(design, centers, rcond=None)
    sigma = float(np.clip(robust_scale(centers - design @ coefficients), *TIMING_SIGMA_BOUNDS))
    converged = False
    maximum_iterations = 300
    _iteration = 0
    for _iteration in range(1, maximum_iterations + 1):
        mean = design @ coefficients
        standardized_lower = (lower - mean) / sigma
        standardized_upper = (upper - mean) / sigma
        probability = interval_probability(standardized_lower, standardized_upper)
        density_lower = np.exp(-0.5 * standardized_lower**2) / math.sqrt(2.0 * math.pi)
        density_upper = np.exp(-0.5 * standardized_upper**2) / math.sqrt(2.0 * math.pi)
        truncated_mean_standard = (density_lower - density_upper) / probability
        truncated_variance_standard = (
            1.0
            + (standardized_lower * density_lower - standardized_upper * density_upper)
            / probability
            - truncated_mean_standard**2
        )
        truncated_variance_standard = np.maximum(truncated_variance_standard, 0.0)
        latent_mean = mean + sigma * truncated_mean_standard
        latent_variance = sigma**2 * truncated_variance_standard
        updated_coefficients, *_ = np.linalg.lstsq(design, latent_mean, rcond=None)
        updated_mean = design @ updated_coefficients
        updated_sigma = float(np.sqrt(np.mean(latent_variance + (latent_mean - updated_mean) ** 2)))
        updated_sigma = float(np.clip(updated_sigma, *TIMING_SIGMA_BOUNDS))
        coefficient_change = float(np.max(np.abs(updated_coefficients - coefficients)))
        sigma_change = abs(updated_sigma - sigma)
        coefficients = updated_coefficients
        sigma = updated_sigma
        if coefficient_change < 1e-10 and sigma_change < 1e-10:
            converged = True
            break
    negative_log_likelihood = -float(
        np.sum(interval_log_probability(lower, upper, design @ coefficients, sigma))
    )
    return {
        "coefficients": coefficients,
        "sigma_samples": sigma,
        "negative_log_likelihood": negative_log_likelihood,
        "converged": converged,
        "optimizer": "deterministic_interval_gaussian_em",
        "iterations": _iteration,
        "sigma_at_bound": bool(
            abs(sigma - TIMING_SIGMA_BOUNDS[0]) < 1e-6 or abs(sigma - TIMING_SIGMA_BOUNDS[1]) < 1e-6
        ),
    }


def predict_polynomial(times_s: np.ndarray, coefficients: np.ndarray) -> np.ndarray:
    prediction: np.ndarray = factorial_basis(times_s, len(coefficients) - 1) @ coefficients
    return prediction


def cfo_metrics(
    observed: np.ndarray, predicted: np.ndarray, predicted_sigma: np.ndarray
) -> dict[str, float | int]:
    selected = np.isfinite(predicted)
    residual = observed[selected] - predicted[selected]
    sigma = predicted_sigma[selected]
    return {
        "count": int(np.count_nonzero(selected)),
        "rms_hz": float(np.sqrt(np.mean(np.square(residual)))),
        "mae_hz": float(np.mean(np.abs(residual))),
        "p95_absolute_hz": float(np.percentile(np.abs(residual), 95)),
        "nominal_95pct_coverage": float(np.mean(np.abs(residual) <= 1.96 * sigma)),
    }


def timing_metrics(
    observed_epoch: np.ndarray,
    nominal_epoch_thirds: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
    predicted: np.ndarray,
    predicted_sigma: np.ndarray,
) -> dict[str, float | int]:
    selected = np.isfinite(predicted)
    mean = predicted[selected]
    sigma = predicted_sigma[selected]
    predicted_epoch = quantize_delay(nominal_epoch_thirds[selected], mean)
    integer_error = observed_epoch[selected] - predicted_epoch
    interval_distance = np.maximum(np.maximum(lower[selected] - mean, mean - upper[selected]), 0.0)
    log_probability = interval_log_probability(lower[selected], upper[selected], mean, sigma)
    return {
        "count": int(np.count_nonzero(selected)),
        "exact_integer_epoch_fraction": float(np.mean(integer_error == 0)),
        "integer_epoch_error_rms_samples": float(np.sqrt(np.mean(np.square(integer_error)))),
        "integer_epoch_error_mae_samples": float(np.mean(np.abs(integer_error))),
        "interval_violation_rms_samples": float(np.sqrt(np.mean(np.square(interval_distance)))),
        "mean_negative_log_probability": -float(np.mean(log_probability)),
        "nominal_95pct_cell_coverage": float(
            np.mean(np.abs(0.5 * (lower[selected] + upper[selected]) - mean) <= 0.5 + 1.96 * sigma)
        ),
    }


def split_masks(
    blocks: np.ndarray, strategy: str
) -> list[tuple[int, np.ndarray, np.ndarray, bool]]:
    output = []
    unique = np.unique(blocks)
    for block in unique:
        validation = blocks == block
        if strategy == "held_calendar_1s_block":
            training = ~validation
        elif strategy == "rolling_origin_next_calendar_block":
            if block < ROLLING_FIRST_VALIDATION_BLOCK:
                continue
            training = blocks < block
        else:
            raise ValueError(f"unknown validation strategy {strategy!r}")
        partial = bool(block in {int(unique[0]), int(unique[-1])})
        output.append((int(block), training, validation, partial))
    return output


def validate_cfo(
    cohort: Cohort, degree: int, strategy: str
) -> tuple[dict[str, Any], np.ndarray, np.ndarray]:
    prediction = np.full(cohort.cfo_hz.shape, np.nan)
    sigma = np.full(cohort.cfo_hz.shape, np.nan)
    rows = []
    for block, training, validation, partial in split_masks(cohort.cfo_calendar_block, strategy):
        model = fit_huber(cohort.cfo_measurement_time_s[training], cohort.cfo_hz[training], degree)
        prediction[validation] = predict_polynomial(
            cohort.cfo_measurement_time_s[validation], model["coefficients"]
        )
        sigma[validation] = float(model["residual_scale"])
        local = cfo_metrics(
            cohort.cfo_hz[validation],
            prediction[validation],
            sigma[validation],
        )
        rows.append(
            {
                "calendar_block": block,
                "interval_s": [float(block), float(block + 1)],
                "partial_edge_block": partial,
                "training_count": int(np.count_nonzero(training)),
                "heldout_count": int(np.count_nonzero(validation)),
                "training_fit_converged": bool(model["converged"]),
                **local,
            }
        )
    return (
        {
            "degree": degree,
            "strategy": strategy,
            "aggregate": cfo_metrics(cohort.cfo_hz, prediction, sigma),
            "all_training_fits_converged": all(bool(row["training_fit_converged"]) for row in rows),
            "blocks": rows,
        },
        prediction,
        sigma,
    )


def validate_timing(
    cohort: Cohort, degree: int, strategy: str
) -> tuple[dict[str, Any], np.ndarray, np.ndarray]:
    prediction = np.full(cohort.delay_center_samples.shape, np.nan)
    sigma = np.full(cohort.delay_center_samples.shape, np.nan)
    rows = []
    for block, training, validation, partial in split_masks(cohort.delay_calendar_block, strategy):
        model = fit_interval_timing(
            cohort.epoch_time_s[training],
            cohort.delay_lower_samples[training],
            cohort.delay_upper_samples[training],
            degree,
        )
        prediction[validation] = predict_polynomial(
            cohort.epoch_time_s[validation], model["coefficients"]
        )
        sigma[validation] = float(model["sigma_samples"])
        local = timing_metrics(
            cohort.observed_epoch[validation],
            cohort.nominal_epoch_thirds[validation],
            cohort.delay_lower_samples[validation],
            cohort.delay_upper_samples[validation],
            prediction[validation],
            sigma[validation],
        )
        rows.append(
            {
                "calendar_block": block,
                "interval_s": [float(block), float(block + 1)],
                "partial_edge_block": partial,
                "training_count": int(np.count_nonzero(training)),
                "heldout_count": int(np.count_nonzero(validation)),
                "training_sigma_samples": float(model["sigma_samples"]),
                "training_sigma_at_bound": bool(model["sigma_at_bound"]),
                "training_fit_converged": bool(model["converged"]),
                **local,
            }
        )
    return (
        {
            "degree": degree,
            "strategy": strategy,
            "aggregate": timing_metrics(
                cohort.observed_epoch,
                cohort.nominal_epoch_thirds,
                cohort.delay_lower_samples,
                cohort.delay_upper_samples,
                prediction,
                sigma,
            ),
            "all_training_fits_converged": all(bool(row["training_fit_converged"]) for row in rows),
            "blocks": rows,
        },
        prediction,
        sigma,
    )


def load_cohort(
    input_path: Path = INPUT_PATH,
    long_evidence_path: Path = LONG_EVIDENCE_PATH,
) -> tuple[Cohort, dict[str, Any], dict[str, Any]]:
    if sha256(input_path) != EXPECTED_INPUT_SHA256:
        raise ValueError("frozen derived cohort hash changed")
    if sha256(long_evidence_path) != EXPECTED_LONG_EVIDENCE_SHA256:
        raise ValueError("authoritative long-run evidence hash changed")
    evidence = load_json(input_path)
    long_evidence = load_json(long_evidence_path)
    if evidence.get("schema") != EXPECTED_SCHEMA:
        raise ValueError("derived cohort schema changed")
    if evidence.get("trajectory_id") != EXPECTED_TRAJECTORY_ID:
        raise ValueError("persisted trajectory identity changed")
    rows = evidence.get("detections")
    if not isinstance(rows, list) or len(rows) != 550:
        raise ValueError("expected exactly 550 frozen detections")
    if evidence.get("input_sha256", {}).get("long_evidence") != EXPECTED_LONG_EVIDENCE_SHA256:
        raise ValueError("derived cohort no longer binds authoritative long evidence")

    observed_epoch = np.asarray([int(row["absolute_epoch_sample"]) for row in rows], dtype=np.int64)
    frame_index, nominal_thirds, center, lower, upper = rational_lattice(
        observed_epoch, int(evidence["reference_epoch_sample"])
    )
    probe_time = np.asarray([float(row["probe_time_s"]) for row in rows])
    detection_sample_start = np.asarray(
        [int(row["detection_sample_start"]) for row in rows], dtype=np.int64
    )
    local_epoch_sample = np.asarray(
        [int(row["local_epoch_sample"]) for row in rows], dtype=np.int64
    )
    if not np.array_equal(detection_sample_start + local_epoch_sample, observed_epoch):
        raise ValueError("absolute and local epoch geometry disagree")
    if not np.allclose(
        detection_sample_start / SAMPLE_RATE_HZ,
        probe_time,
        rtol=0.0,
        atol=1e-12,
    ):
        raise ValueError("probe timestamp and detection sample start disagree")
    centroid_geometry = [
        glrt64_correlation_centroid_local_sample(int(epoch)) for epoch in local_epoch_sample
    ]
    cfo_centroid_local = np.asarray([item[0] for item in centroid_geometry])
    cfo_supported_frame_count = np.asarray([item[1] for item in centroid_geometry], dtype=np.int64)
    cfo_measurement_time = (
        detection_sample_start.astype(float) + cfo_centroid_local
    ) / SAMPLE_RATE_HZ
    epoch_time = observed_epoch.astype(float) / SAMPLE_RATE_HZ
    cohort = Cohort(
        probe_time_s=probe_time,
        epoch_time_s=epoch_time,
        cfo_measurement_time_s=cfo_measurement_time,
        cfo_centroid_local_sample=cfo_centroid_local,
        cfo_supported_frame_count=cfo_supported_frame_count,
        cfo_hz=np.asarray([float(row["tracking_cfo_hz"]) for row in rows]),
        observed_epoch=observed_epoch,
        frame_index=frame_index,
        nominal_epoch_thirds=nominal_thirds,
        delay_center_samples=center,
        delay_lower_samples=lower,
        delay_upper_samples=upper,
        cfo_calendar_block=np.floor(cfo_measurement_time).astype(int),
        delay_calendar_block=np.floor(epoch_time).astype(int),
        exact_score=np.asarray([float(row["exact_score"]) for row in rows]),
        control_score=np.asarray([float(row["control_score"]) for row in rows]),
        margin=np.asarray([float(row["margin"]) for row in rows]),
    )
    return cohort, evidence, long_evidence


def load_frame_cfo_diagnostic(
    frame_rows_path: Path = FRAME_ROWS_PATH,
) -> dict[str, Any]:
    """Load the frame-rate lane with a fixed diagnostic-only support mask."""

    if sha256(frame_rows_path) != EXPECTED_FRAME_ROWS_SHA256:
        raise ValueError("frame-row ledger hash changed")
    accounting = {
        "total_rows": 0,
        "outside_interval": 0,
        "not_primary_supported": 0,
        "primary_search_boundary": 0,
        "acquisition_overlap": 0,
        "pre_acquisition_backprojection": 0,
        "anchor_not_causally_available": 0,
        "base_mask_rows": 0,
        "even_missing": 0,
        "odd_missing_or_search_boundary": 0,
    }
    even_time: list[float] = []
    even_cfo: list[float] = []
    odd_time: list[float] = []
    odd_cfo: list[float] = []
    with frame_rows_path.open("r", encoding="utf-8") as source:
        for line in source:
            row = json.loads(line)
            accounting["total_rows"] += 1
            time_s = float(row["reference_sample"]) / SAMPLE_RATE_HZ
            if not math.isclose(
                time_s,
                float(row["reference_time_s"]),
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                raise ValueError("frame event sample and timestamp disagree")
            if not (37.575 <= time_s < 51.4):
                accounting["outside_interval"] += 1
                continue
            if not bool(row["primary_supported"]):
                accounting["not_primary_supported"] += 1
                continue
            if bool(row["primary_search_boundary"]):
                accounting["primary_search_boundary"] += 1
                continue
            if bool(row["acquisition_overlap"]) or bool(row["any_selected_acquisition_overlap"]):
                accounting["acquisition_overlap"] += 1
                continue
            if bool(row["pre_acquisition_backprojection"]):
                accounting["pre_acquisition_backprojection"] += 1
                continue
            if not bool(row["anchor_causally_available"]):
                accounting["anchor_not_causally_available"] += 1
                continue
            accounting["base_mask_rows"] += 1
            even_value = row["even_absolute_cfo_hz"]
            if even_value is None or not math.isfinite(float(even_value)):
                accounting["even_missing"] += 1
            else:
                even_time.append(time_s)
                even_cfo.append(float(even_value))
            odd_value = row["odd_absolute_cfo_hz"]
            if (
                odd_value is None
                or not math.isfinite(float(odd_value))
                or bool(row["odd_search_boundary"])
            ):
                accounting["odd_missing_or_search_boundary"] += 1
            else:
                odd_time.append(time_s)
                odd_cfo.append(float(odd_value))
    return {
        "even_event_time_s": np.asarray(even_time),
        "even_cfo_hz": np.asarray(even_cfo),
        "odd_event_time_s": np.asarray(odd_time),
        "odd_cfo_hz": np.asarray(odd_cfo),
        "accounting": accounting,
    }


def frame_lane_metrics(
    times_s: np.ndarray, values_hz: np.ndarray, coefficients: np.ndarray
) -> dict[str, float | int]:
    residual = values_hz - predict_polynomial(times_s, coefficients)
    return {
        "count": int(values_hz.size),
        "residual_rms_hz": float(np.sqrt(np.mean(np.square(residual)))),
        "residual_mae_hz": float(np.mean(np.abs(residual))),
        "residual_median_hz": float(np.median(residual)),
        "residual_p95_absolute_hz": float(np.percentile(np.abs(residual), 95)),
    }


def parameter_dict(coefficients: np.ndarray, prefix: str) -> dict[str, float]:
    suffixes = ("value", "rate", "acceleration", "jerk")
    return {f"{prefix}_{suffixes[index]}": float(value) for index, value in enumerate(coefficients)}


def deletion_stability(cohort: Cohort) -> dict[str, Any]:
    cfo_values = []
    delay_values = []
    for block in np.unique(cohort.cfo_calendar_block):
        selected = cohort.cfo_calendar_block != block
        cfo_model = fit_huber(
            cohort.cfo_measurement_time_s[selected],
            cohort.cfo_hz[selected],
            PRIMARY_CFO_DEGREE,
        )
        cfo_values.append(cfo_model["coefficients"])
    for block in np.unique(cohort.delay_calendar_block):
        selected = cohort.delay_calendar_block != block
        delay_model = fit_interval_timing(
            cohort.epoch_time_s[selected],
            cohort.delay_lower_samples[selected],
            cohort.delay_upper_samples[selected],
            PRIMARY_DELAY_DEGREE,
        )
        delay_values.append(delay_model["coefficients"])
    output: dict[str, Any] = {}
    for name, values, labels in (
        (
            "cfo",
            np.asarray(cfo_values),
            ("value_hz", "rate_hz_s", "acceleration_hz_s2", "jerk_hz_s3"),
        ),
        (
            "delay",
            np.asarray(delay_values),
            ("value_samples", "rate_samples_s", "acceleration_samples_s2"),
        ),
    ):
        output[name] = {
            label: {
                "minimum": float(np.min(values[:, index])),
                "maximum": float(np.max(values[:, index])),
                "standard_deviation": float(np.std(values[:, index])),
                "sign_consistent": bool(
                    np.all(values[:, index] >= 0.0) or np.all(values[:, index] <= 0.0)
                ),
            }
            for index, label in enumerate(labels)
        }
    return output


def synthetic_check() -> dict[str, Any]:
    generator = np.random.default_rng(0xC0F0D3)
    times = np.linspace(37.6, 51.35, 550)
    delay_truth = np.asarray([12.0, 1.4, -0.72])
    delay_mean = predict_polynomial(times, delay_truth)
    reference_epoch = 94_002_005
    indexes = np.arange(550, dtype=np.int64) * 19
    nominal_thirds = 3 * reference_epoch + 10_000 * indexes
    latent = delay_mean + generator.normal(0.0, 0.12, size=times.size)
    observed_epoch = quantize_delay(nominal_thirds, latent)
    _, _, _, lower, upper = rational_lattice(observed_epoch, reference_epoch)
    delay_fit = fit_interval_timing(times, lower, upper, 2)

    cfo_truth = np.asarray([-118_000.0, -3_550.0, -18.0, 2.4])
    cfo = predict_polynomial(times, cfo_truth)
    cfo += generator.normal(0.0, 35.0, size=times.size)
    outliers = generator.choice(times.size, size=12, replace=False)
    cfo[outliers] += generator.normal(0.0, 350.0, size=outliers.size)
    cfo_fit = fit_huber(times, cfo, 3)
    delay_error = np.asarray(delay_fit["coefficients"]) - delay_truth
    cfo_error = np.asarray(cfo_fit["coefficients"]) - cfo_truth
    return {
        "generator": (
            "deterministic independent Gaussian-before-quantizer timing data and "
            "Gaussian-plus-outlier CFO data on the frozen time geometry"
        ),
        "delay_truth": delay_truth.tolist(),
        "delay_estimate": np.asarray(delay_fit["coefficients"]).tolist(),
        "delay_parameter_error": delay_error.tolist(),
        "cfo_truth": cfo_truth.tolist(),
        "cfo_estimate": np.asarray(cfo_fit["coefficients"]).tolist(),
        "cfo_parameter_error": cfo_error.tolist(),
        "accepted": bool(
            abs(delay_error[1]) < 0.03
            and abs(delay_error[2]) < 0.03
            and abs(cfo_error[1]) < 10.0
            and abs(cfo_error[2]) < 5.0
        ),
    }


def render_plot(
    path: Path,
    cohort: Cohort,
    full_cfo: dict[int, dict[str, Any]],
    full_delay: dict[int, dict[str, Any]],
    cfo_validation: dict[str, dict[int, dict[str, Any]]],
    timing_validation: dict[str, dict[int, dict[str, Any]]],
    primary_cfo_prediction: np.ndarray,
    primary_delay_prediction: np.ndarray,
) -> None:
    figure, axes = plt.subplots(3, 2, figsize=(14, 11), constrained_layout=True)
    time_grid = np.linspace(
        min(float(cohort.epoch_time_s[0]), float(cohort.cfo_measurement_time_s[0])),
        max(float(cohort.epoch_time_s[-1]), float(cohort.cfo_measurement_time_s[-1])),
        800,
    )

    ax = axes[0, 0]
    ax.scatter(
        cohort.cfo_measurement_time_s,
        cohort.cfo_hz,
        s=7,
        color="#5b4bb7",
        alpha=0.45,
        label="selected 20 ms direct CFO",
    )
    for degree, color, label in (
        (1, "#777777", "robust line"),
        (2, "#2b6cb0", "robust quadratic"),
        (3, "#b45309", "primary robust cubic"),
    ):
        ax.plot(
            time_grid,
            predict_polynomial(time_grid, full_cfo[degree]["coefficients"]),
            color=color,
            linewidth=1.5 if degree == 3 else 1.0,
            label=label,
        )
    ax.set_title("Direct CFO uses the actual GLRT64 correlation centroid")
    ax.set_ylabel("Selected CFO (Hz)")
    ax.grid(alpha=0.22)
    ax.legend(fontsize=8)

    ax = axes[0, 1]
    ax.scatter(
        cohort.epoch_time_s,
        cohort.delay_center_samples,
        s=8,
        color="#5b4bb7",
        alpha=0.5,
        label="integer GLRT epoch − rational lattice",
    )
    delay_curve = predict_polynomial(time_grid, full_delay[PRIMARY_DELAY_DEGREE]["coefficients"])
    ax.plot(
        time_grid,
        delay_curve,
        color="#b45309",
        linewidth=1.8,
        label="primary interval-likelihood quadratic",
    )
    ax.set_title("Timing teeth are ±0.5-sample censoring cells, not analog samples")
    ax.set_ylabel("Template-relative delay (samples)")
    ax.grid(alpha=0.22)
    ax.legend(fontsize=8)

    ax = axes[1, 0]
    selected = np.isfinite(primary_cfo_prediction)
    ax.scatter(
        cohort.cfo_measurement_time_s[selected],
        cohort.cfo_hz[selected] - primary_cfo_prediction[selected],
        s=9,
        color="#2b6cb0",
        alpha=0.55,
    )
    ax.axhline(0.0, color="black", linewidth=0.8)
    cfo_roll = cfo_validation["rolling_origin_next_calendar_block"][3]["aggregate"]
    ax.set_title(f"True rolling-origin CFO residual · RMS {cfo_roll['rms_hz']:.1f} Hz")
    ax.set_ylabel("Held-out CFO residual (Hz)")
    ax.grid(alpha=0.22)

    ax = axes[1, 1]
    selected = np.isfinite(primary_delay_prediction)
    predicted_epoch = quantize_delay(
        cohort.nominal_epoch_thirds[selected], primary_delay_prediction[selected]
    )
    integer_error = cohort.observed_epoch[selected] - predicted_epoch
    ax.scatter(
        cohort.epoch_time_s[selected],
        integer_error,
        s=12,
        color=np.where(integer_error == 0, "#2b6cb0", "#c2410c"),
        alpha=0.65,
    )
    ax.axhline(0.0, color="black", linewidth=0.8)
    timing_roll = timing_validation["rolling_origin_next_calendar_block"][2]["aggregate"]
    ax.set_title(
        "Rolling-origin quantized epoch errors · exact "
        f"{100 * timing_roll['exact_integer_epoch_fraction']:.1f}%"
    )
    ax.set_ylabel("Observed − predicted integer epoch (samples)")
    ax.grid(alpha=0.22)

    ax = axes[2, 0]
    strategies = (
        "held_calendar_1s_block",
        "rolling_origin_next_calendar_block",
    )
    x = np.arange(3)
    width = 0.36
    for offset, strategy, color, label in (
        (-width / 2, strategies[0], "#2b6cb0", "held 1 s block"),
        (width / 2, strategies[1], "#b45309", "rolling origin"),
    ):
        values = [cfo_validation[strategy][degree]["aggregate"]["rms_hz"] for degree in (1, 2, 3)]
        ax.bar(x + offset, values, width, color=color, label=label)
    ax.set_xticks(x, ("line", "quadratic", "cubic"))
    ax.set_ylabel("Held-out CFO RMS (Hz)")
    ax.set_title("CFO degree comparison on identical temporal folds")
    ax.grid(axis="y", alpha=0.22)
    ax.legend(fontsize=8)

    ax = axes[2, 1]
    x = np.arange(2)
    for offset, strategy, color, label in (
        (-width / 2, strategies[0], "#2b6cb0", "held 1 s block"),
        (width / 2, strategies[1], "#b45309", "rolling origin"),
    ):
        values = [
            100 * timing_validation[strategy][degree]["aggregate"]["exact_integer_epoch_fraction"]
            for degree in (1, 2)
        ]
        ax.bar(x + offset, values, width, color=color, label=label)
    ax.set_xticks(x, ("delay + rate", "delay + rate + acceleration"))
    ax.set_ylabel("Exact held-out integer epoch (%)")
    ax.set_title("Acceleration is required; cubic timing was not promoted")
    ax.grid(axis="y", alpha=0.22)
    ax.legend(fontsize=8)

    figure.suptitle(
        "Aug-25 branch · separable CFO and quantized frame-delay dynamics\n"
        "fixed 10,000/3-sample lattice · candidate-conditioned empirical model",
        fontsize=14,
    )
    figure.supxlabel(
        "No physical-Doppler, propagation-delay, SFO, or pseudorange claim; "
        "CFO and timing share selection but have zero cross-observation update.",
        fontsize=8,
    )
    figure.savefig(path, dpi=180, metadata={"Software": "Matplotlib"})
    plt.close(figure)


def render_frame_cfo_diagnostic(
    path: Path,
    frame_lane: dict[str, Any],
    cfo_coefficients: np.ndarray,
) -> None:
    even_time = frame_lane["even_event_time_s"]
    even_cfo = frame_lane["even_cfo_hz"]
    odd_time = frame_lane["odd_event_time_s"]
    odd_cfo = frame_lane["odd_cfo_hz"]
    grid = np.linspace(37.575, 51.4, 1000)
    curve = predict_polynomial(grid, cfo_coefficients)
    even_residual = even_cfo - predict_polynomial(even_time, cfo_coefficients)
    odd_residual = odd_cfo - predict_polynomial(odd_time, cfo_coefficients)

    figure, axes = plt.subplots(
        2,
        1,
        figsize=(14, 8),
        sharex=True,
        constrained_layout=True,
        gridspec_kw={"height_ratios": (1.35, 1.0)},
    )
    ax = axes[0]
    ax.scatter(
        even_time,
        even_cfo,
        s=4,
        alpha=0.22,
        color="#2b6cb0",
        linewidths=0,
        label=f"even-Qin frame CFO · n={len(even_cfo)}",
    )
    ax.scatter(
        odd_time,
        odd_cfo,
        s=4,
        alpha=0.22,
        color="#c05621",
        linewidths=0,
        label=f"odd-Qin frame CFO · n={len(odd_cfo)}",
    )
    ax.plot(
        grid,
        curve,
        color="#171717",
        linewidth=1.8,
        label="primary CFO cubic selected only from 550 direct-GLRT rows",
    )
    ax.set_ylabel("CFO (Hz)")
    ax.set_title("750 Hz frame lane is a diagnostic—not a model-selection input")
    ax.grid(alpha=0.2)
    ax.legend(fontsize=8)

    ax = axes[1]
    ax.scatter(
        even_time,
        even_residual,
        s=4,
        alpha=0.24,
        color="#2b6cb0",
        linewidths=0,
        label=(f"even residual · RMS {np.sqrt(np.mean(np.square(even_residual))):.1f} Hz"),
    )
    ax.scatter(
        odd_time,
        odd_residual,
        s=4,
        alpha=0.24,
        color="#c05621",
        linewidths=0,
        label=(f"odd residual · RMS {np.sqrt(np.mean(np.square(odd_residual))):.1f} Hz"),
    )
    ax.axhline(0.0, color="#171717", linewidth=0.8)
    ax.set_xlabel("Time from dwell start (s)")
    ax.set_ylabel("Frame CFO − direct-CFO model (Hz)")
    ax.set_title(
        "Mask: causal anchor, supported estimator, no acquisition overlap, "
        "no search boundary or backprojection"
    )
    ax.grid(alpha=0.2)
    ax.legend(fontsize=8)
    figure.suptitle(
        "Frame-rate even/odd CFO diagnostic against the frozen direct-CFO model\n"
        "same candidate-conditioned branch · no physical-Doppler claim",
        fontsize=14,
    )
    figure.savefig(path, dpi=180, metadata={"Software": "Matplotlib"})
    plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=INPUT_PATH)
    parser.add_argument("--long-evidence", type=Path, default=LONG_EVIDENCE_PATH)
    parser.add_argument("--frame-rows", type=Path, default=FRAME_ROWS_PATH)
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    args = parser.parse_args()
    output_root: Path = args.output_root
    output_root.mkdir(parents=True, exist_ok=True)
    cohort, input_evidence, long_evidence = load_cohort(args.input, args.long_evidence)
    frame_lane = load_frame_cfo_diagnostic(args.frame_rows)
    full_cfo = {
        degree: fit_huber(cohort.cfo_measurement_time_s, cohort.cfo_hz, degree)
        for degree in (1, 2, 3)
    }
    full_delay = {
        degree: fit_interval_timing(
            cohort.epoch_time_s,
            cohort.delay_lower_samples,
            cohort.delay_upper_samples,
            degree,
        )
        for degree in (1, 2, 3)
    }

    cfo_validation: dict[str, dict[int, dict[str, Any]]] = {}
    timing_validation: dict[str, dict[int, dict[str, Any]]] = {}
    validation_arrays: dict[str, dict[str, np.ndarray]] = {}
    for strategy in (
        "held_calendar_1s_block",
        "rolling_origin_next_calendar_block",
    ):
        cfo_validation[strategy] = {}
        timing_validation[strategy] = {}
        for degree in (1, 2, 3):
            result, prediction, sigma = validate_cfo(cohort, degree, strategy)
            cfo_validation[strategy][degree] = result
            if degree == PRIMARY_CFO_DEGREE:
                validation_arrays[f"cfo_{strategy}"] = {
                    "prediction": prediction,
                    "sigma": sigma,
                }
        for degree in (1, 2, 3):
            result, prediction, sigma = validate_timing(cohort, degree, strategy)
            timing_validation[strategy][degree] = result
            if degree == PRIMARY_DELAY_DEGREE:
                validation_arrays[f"delay_{strategy}"] = {
                    "prediction": prediction,
                    "sigma": sigma,
                }

    primary_cfo = full_cfo[PRIMARY_CFO_DEGREE]
    primary_delay = full_delay[PRIMARY_DELAY_DEGREE]
    deletion = deletion_stability(cohort)
    synthetic = synthetic_check()
    rolling_cfo_prediction = validation_arrays["cfo_rolling_origin_next_calendar_block"][
        "prediction"
    ]
    rolling_delay_prediction = validation_arrays["delay_rolling_origin_next_calendar_block"][
        "prediction"
    ]

    rows_path = output_root / "joint-model-rows.jsonl"
    with rows_path.open("w", encoding="utf-8") as sink:
        full_cfo_prediction = predict_polynomial(
            cohort.cfo_measurement_time_s, primary_cfo["coefficients"]
        )
        full_delay_prediction = predict_polynomial(
            cohort.epoch_time_s, primary_delay["coefficients"]
        )
        for index in range(len(cohort.cfo_hz)):
            row = {
                "row_index": index,
                "probe_time_s": float(cohort.probe_time_s[index]),
                "epoch_time_s": float(cohort.epoch_time_s[index]),
                "delay_calendar_block": int(cohort.delay_calendar_block[index]),
                "cfo_measurement_time_s": float(cohort.cfo_measurement_time_s[index]),
                "cfo_calendar_block": int(cohort.cfo_calendar_block[index]),
                "cfo_centroid_local_sample": float(cohort.cfo_centroid_local_sample[index]),
                "cfo_supported_frame_count": int(cohort.cfo_supported_frame_count[index]),
                "cfo_supported_symbol_observation_count": int(
                    cohort.cfo_supported_frame_count[index]
                    * (GLRT_LAST_SYMBOL - GLRT_FIRST_SYMBOL + 1)
                ),
                "frame_index": int(cohort.frame_index[index]),
                "absolute_epoch_sample": int(cohort.observed_epoch[index]),
                "nominal_epoch_thirds": int(cohort.nominal_epoch_thirds[index]),
                "delay_quantizer_cell_samples": [
                    float(cohort.delay_lower_samples[index]),
                    float(cohort.delay_upper_samples[index]),
                ],
                "tracking_cfo_hz": float(cohort.cfo_hz[index]),
                "full_primary_cfo_hz": float(full_cfo_prediction[index]),
                "full_primary_delay_samples": float(full_delay_prediction[index]),
                "rolling_cfo_prediction_hz": (
                    None
                    if not np.isfinite(rolling_cfo_prediction[index])
                    else float(rolling_cfo_prediction[index])
                ),
                "rolling_delay_prediction_samples": (
                    None
                    if not np.isfinite(rolling_delay_prediction[index])
                    else float(rolling_delay_prediction[index])
                ),
                "exact_score": float(cohort.exact_score[index]),
                "control_score": float(cohort.control_score[index]),
                "margin": float(cohort.margin[index]),
            }
            sink.write(json.dumps(row, sort_keys=True) + "\n")

    plot_path = output_root / "joint-cfo-delay-acceleration.png"
    render_plot(
        plot_path,
        cohort,
        full_cfo,
        full_delay,
        cfo_validation,
        timing_validation,
        rolling_cfo_prediction,
        rolling_delay_prediction,
    )
    frame_plot_path = output_root / "frame-cfo-diagnostic.png"
    render_frame_cfo_diagnostic(
        frame_plot_path,
        frame_lane,
        np.asarray(primary_cfo["coefficients"]),
    )

    primary_cfo_coefficients = np.asarray(primary_cfo["coefficients"])
    primary_delay_coefficients = np.asarray(primary_delay["coefficients"])
    cfo_per_delay_rate_hz_per_sample = RF_CENTER_HZ / SAMPLE_RATE_HZ
    timing_equivalent_cfo_rate_hz_s = float(
        cfo_per_delay_rate_hz_per_sample * primary_delay_coefficients[2]
    )
    evidence = {
        "schema": "org.leo.research.joint-cfo-delay-acceleration-prototype/v1",
        "status": "bounded_candidate_conditioned_research_prototype",
        "input": {
            "path": str(args.input),
            "sha256": EXPECTED_INPUT_SHA256,
            "schema": EXPECTED_SCHEMA,
            "long_evidence_path": str(args.long_evidence),
            "long_evidence_sha256": EXPECTED_LONG_EVIDENCE_SHA256,
            "frame_rows_path": str(args.frame_rows),
            "frame_rows_sha256": EXPECTED_FRAME_ROWS_SHA256,
            "trajectory_id": EXPECTED_TRAJECTORY_ID,
            "recording_manifest_sha256": input_evidence["input_sha256"]["recording_manifest"],
            "pilot_scan_sha256": input_evidence["input_sha256"]["pilot_scan"],
            "trajectory_bank_sha256": input_evidence["input_sha256"]["final_trajectory_bank"],
            "interval": input_evidence["interval"],
            "detection_count": len(cohort.cfo_hz),
            "candidate_only": True,
            "counter_continuity": long_evidence["counter_continuity"],
            "refill_boundary_count": len(long_evidence["refill_audit_boundary_samples"]),
        },
        "predeclared_primary_model": {
            "reference_time_s": REFERENCE_TIME_S,
            "state": [
                "cfo_hz",
                "cfo_rate_hz_s",
                "cfo_acceleration_hz_s2",
                "cfo_jerk_hz_s3",
                "delay_samples",
                "delay_rate_samples_s",
                "delay_acceleration_samples_s2",
            ],
            "cfo_equation": (
                "f(t)=f0+f1*tau+f2*tau^2/2+f3*tau^3/6, "
                "tau=t-44.4875 s; Huber IRLS on direct tracking_cfo_hz at "
                "the actual selected-correlation centroid only"
            ),
            "delay_equation": (
                "d(t)=d0+d1*tau+d2*tau^2/2, tau=t-44.4875 s; "
                "delta>0 means later observed epoch relative to the fixed lattice"
            ),
            "rational_lattice_equation": (
                "L_k=e_ref+k*(10000/3) samples; "
                "k=round((e_i-e_ref)/(10000/3)) is frozen from observed epoch"
            ),
            "timing_observation_likelihood": (
                "P(e_i|d,sigma)=Phi((e_i+0.5-L_k-d(t_i))/sigma)-Phi((e_i-0.5-L_k-d(t_i))/sigma)"
            ),
            "joint_semantics": (
                "block-diagonal empirical state and factorized computation; CFO and "
                "timing have zero cross-observation terms and are not converted"
            ),
            "transition_equation": (
                "x(t+dt)=blockdiag(F_CJ(dt),F_CA(dt))*x(t), where each "
                "upper-triangular F has dt^k/k! entries; Q=0 inside each batch "
                "fit and every temporal fold is refit from its training rows only"
            ),
        },
        "measurement_time_support": {
            "direct_cfo": {
                "window_sample_count": GLRT_WINDOW_SAMPLE_COUNT,
                "selected_symbols_inclusive": [GLRT_FIRST_SYMBOL, GLRT_LAST_SYMBOL],
                "frame_start_rule": ("local_epoch_sample+round(frame_index*sample_rate_hz/750)"),
                "symbol_center_rule": (
                    "frame_start+round(symbol*sample_rate_hz*4.4e-6)+(symbol_sample_count-1)/2"
                ),
                "support_rule": (
                    "all symbols 2..65 must be complete; selection stops before "
                    "the first incomplete selected-symbol frame"
                ),
                "absolute_time_rule": (
                    "(detection_sample_start+mean(all supported symbol centers))/sample_rate_hz"
                ),
                "supported_frame_count": {
                    "minimum": int(np.min(cohort.cfo_supported_frame_count)),
                    "maximum": int(np.max(cohort.cfo_supported_frame_count)),
                },
                "offset_from_probe_time_s": {
                    "minimum": float(np.min(cohort.cfo_measurement_time_s - cohort.probe_time_s)),
                    "median": float(np.median(cohort.cfo_measurement_time_s - cohort.probe_time_s)),
                    "maximum": float(np.max(cohort.cfo_measurement_time_s - cohort.probe_time_s)),
                },
            },
            "delay": (
                "absolute_epoch_sample/sample_rate_hz; interval-censored integer "
                "epoch remains separate from the CFO correlation-centroid time"
            ),
            "frame_rate_diagnostic": (
                "reference_sample/sample_rate_hz, the estimator's frame event time"
            ),
        },
        "full_data_descriptive_fit": {
            "primary_cfo": {
                **parameter_dict(primary_cfo_coefficients, "cfo"),
                "robust_residual_scale_hz": float(primary_cfo["residual_scale"]),
                "converged": bool(primary_cfo["converged"]),
            },
            "primary_delay": {
                **parameter_dict(primary_delay_coefficients, "delay"),
                "interval_sigma_samples": float(primary_delay["sigma_samples"]),
                "sigma_at_bound": bool(primary_delay["sigma_at_bound"]),
                "converged": bool(primary_delay["converged"]),
            },
            "secondary_models": {
                "cfo": {
                    str(degree): {
                        **parameter_dict(np.asarray(full_cfo[degree]["coefficients"]), "cfo"),
                        "robust_residual_scale_hz": float(full_cfo[degree]["residual_scale"]),
                    }
                    for degree in (1, 2, 3)
                },
                "delay": {
                    str(degree): {
                        **parameter_dict(np.asarray(full_delay[degree]["coefficients"]), "delay"),
                        "interval_sigma_samples": float(full_delay[degree]["sigma_samples"]),
                        "sigma_at_bound": bool(full_delay[degree]["sigma_at_bound"]),
                    }
                    for degree in (1, 2, 3)
                },
            },
        },
        "doppler_equivalent_rate_diagnostic": {
            "used_for_fit_or_selection": False,
            "rf_center_hz": RF_CENTER_HZ,
            "sample_rate_hz": SAMPLE_RATE_HZ,
            "frame_rate_hz": FRAME_RATE_HZ,
            "cfo_per_delay_rate_hz_per_sample": cfo_per_delay_rate_hz_per_sample,
            "timing_acceleration_same_sign_cfo_rate_hz_s": (timing_equivalent_cfo_rate_hz_s),
            "direct_cfo_rate_at_reference_hz_s": float(primary_cfo_coefficients[1]),
            "same_sign_rate_difference_hz_s": float(
                primary_cfo_coefficients[1] - timing_equivalent_cfo_rate_hz_s
            ),
            "extra_frame_length_samples_at_reference": float(
                primary_delay_coefficients[1] / FRAME_RATE_HZ
            ),
            "extra_frame_length_ns_at_reference": float(
                primary_delay_coefficients[1] / FRAME_RATE_HZ / SAMPLE_RATE_HZ * 1e9
            ),
            "extra_frame_length_rate_samples_per_frame_s": float(
                primary_delay_coefficients[2] / FRAME_RATE_HZ
            ),
            "extra_frame_length_rate_ns_per_frame_s": float(
                primary_delay_coefficients[2] / FRAME_RATE_HZ / SAMPLE_RATE_HZ * 1e9
            ),
            "sign_note": (
                "repository same-sign timing convention; conventional observed-minus-"
                "nominal propagation Doppler uses the opposite sign"
            ),
            "interpretation": (
                "post-fit conditional diagnostic only; direct CFO and timing share "
                "candidate windows and are not independent, while transmitter clocks, "
                "receiver clocks, LO/LNB drift, and channel remain confounded"
            ),
        },
        "temporal_validation": {
            "calendar_block_semantics": (
                "CFO uses floor(cfo_measurement_time_s); delay uses "
                "floor(epoch_time_s); blocks 37 and 51 are explicit partial edges"
            ),
            "rolling_origin_semantics": (
                "for validation block b>=43, fit only blocks <b and predict b; "
                "no future rows or heldout centering"
            ),
            "cfo": cfo_validation,
            "timing": timing_validation,
        },
        "one_calendar_block_deletion_coefficient_stability": deletion,
        "selection_control_diagnostic": {
            "rolled_qin_control_is_independent_model_gate": False,
            "control_beats_exact_count": int(
                np.count_nonzero(cohort.control_score >= cohort.exact_score)
            ),
            "minimum_selected_exact_minus_control_margin": float(np.min(cohort.margin)),
            "note": (
                "all rows were preselected with positive GLRT margin; this reports "
                "selection support and is not a fresh heldout rolled-Qin null"
            ),
        },
        "frame_rate_cfo_diagnostic": {
            "used_for_model_fit_or_selection": False,
            "mask": (
                "37.575<=reference_sample/sample_rate_hz<51.4; primary_supported; "
                "not primary_search_boundary; no acquisition overlap; "
                "not pre_acquisition_backprojection; anchor_causally_available; "
                "finite lane CFO; odd lane additionally not odd_search_boundary"
            ),
            "accounting": frame_lane["accounting"],
            "even": frame_lane_metrics(
                frame_lane["even_event_time_s"],
                frame_lane["even_cfo_hz"],
                primary_cfo_coefficients,
            ),
            "odd": frame_lane_metrics(
                frame_lane["odd_event_time_s"],
                frame_lane["odd_cfo_hz"],
                primary_cfo_coefficients,
            ),
            "note": (
                "the frame lane is measured at 750 Hz and compared only after the "
                "primary cubic was frozen from the 550 direct-CFO rows"
            ),
        },
        "synthetic_algorithm_check": synthetic,
        "gates": {
            "input_hashes_validated": True,
            "rational_lattice_and_interval_censoring_used": True,
            "true_rolling_origin_reported": True,
            "cfo_and_timing_cross_update_disabled": True,
            "timing_interval_sigma_interior": bool(not primary_delay["sigma_at_bound"]),
            "primary_temporal_fit_optimizers_converged": all(
                cfo_validation[strategy][PRIMARY_CFO_DEGREE]["all_training_fits_converged"]
                and timing_validation[strategy][PRIMARY_DELAY_DEGREE]["all_training_fits_converged"]
                for strategy in (
                    "held_calendar_1s_block",
                    "rolling_origin_next_calendar_block",
                )
            ),
            "primary_timing_fold_sigmas_interior": all(
                not bool(row["training_sigma_at_bound"])
                for strategy in (
                    "held_calendar_1s_block",
                    "rolling_origin_next_calendar_block",
                )
                for row in timing_validation[strategy][PRIMARY_DELAY_DEGREE]["blocks"]
            ),
            "fresh_heldout_rolled_qin_null_available": False,
            "cross_edge_or_receiver_channel_stability_available": False,
            "absolute_timing_or_physical_doppler_promotable": False,
        },
        "interpretation_limits": [
            "The 550 rows are trajectory-conditioned joint all-Qin GLRT selections, "
            "not iid or unbiased frame observations.",
            "Direct CFO and epoch share candidate windows but use correlation-centroid "
            "and epoch times respectively; zero cross-update prevents circular fitting "
            "but does not make their evidence independent.",
            "Frame indexes are recovered conditional on observed integer epochs; this "
            "prototype does not test arbitrary full-frame reacquisition.",
            "Delay is template/lattice-relative. Transmitter frame clock, receiver sample "
            "clock, constant channel group delay, and time-varying channel phase remain "
            "confounded; no TOA, pseudorange, range, or physical SFO is identified.",
            "CFO includes transmitter carrier, receiver LO, and LNB drift; its polynomial "
            "derivatives are empirical and are not claimed physical Doppler.",
            "Accepted Pluto refills remain one lossless device-coordinate segment with "
            "zero gaps, missing samples, or overflows; refills are not treated as causal "
            "resets in this experiment.",
            "A fresh odd-Qin or separately acquired rolled-Qin fold and cross-edge/receiver "
            "channel stability evidence are required before promotion.",
        ],
    }
    evidence_path = output_root / "joint-cfo-delay-acceleration-evidence.json"
    evidence_path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "schema": "org.leo.research.joint-cfo-delay-acceleration-manifest/v1",
        "artifacts": {
            "script": {
                "path": "tools/prototype_joint_cfo_delay_acceleration.py",
                "sha256": sha256(Path(__file__)),
            },
            "evidence": {
                "path": str(evidence_path),
                "sha256": sha256(evidence_path),
            },
            "rows": {"path": str(rows_path), "sha256": sha256(rows_path)},
            "plot": {"path": str(plot_path), "sha256": sha256(plot_path)},
            "frame_cfo_plot": {
                "path": str(frame_plot_path),
                "sha256": sha256(frame_plot_path),
            },
        },
    }
    manifest_path = output_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(manifest_path)


if __name__ == "__main__":
    main()
