"""Robust common-rate fits for parity-split multi-radio frame CFO points."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class MultiRadioFramePoint:
    """One even-trained and odd-held-out frame-CFO observation."""

    point_id: str
    path_id: str
    physical_radio_id: str
    time_s: float
    even_cfo_hz: float
    odd_cfo_hz: float | None
    even_sigma_hz: float | None = None

    def __post_init__(self) -> None:
        if not self.point_id or not self.path_id or not self.physical_radio_id:
            raise ValueError("frame point identities must be nonempty")
        if not all(math.isfinite(value) for value in (self.time_s, self.even_cfo_hz)):
            raise ValueError("frame point values must be finite")
        if self.odd_cfo_hz is not None and not math.isfinite(self.odd_cfo_hz):
            raise ValueError("odd-Qin response must be finite when present")
        if self.even_sigma_hz is not None and (
            not math.isfinite(self.even_sigma_hz) or self.even_sigma_hz <= 0.0
        ):
            raise ValueError("frame uncertainty must be finite and positive")


@dataclass(frozen=True, slots=True)
class CommonRateFit:
    """One shared slope with a separate intercept for every receiver path."""

    reference_time_s: float
    rate_hz_s: float
    path_intercepts_hz: tuple[tuple[str, float], ...]
    point_count: int
    path_count: int
    residual_rms_hz: float
    residual_mad_hz: float
    iteration_count: int
    converged: bool
    fit_symbols: str = "even Qin only"
    odd_symbols_influenced_fit: bool = False
    per_path_drift_fitted: bool = False

    def intercept(self, path_id: str) -> float:
        for candidate, value in self.path_intercepts_hz:
            if candidate == path_id:
                return value
        raise ValueError(f"path is absent from common-rate fit: {path_id}")

    def predict(self, path_id: str, time_s: float) -> float:
        if not math.isfinite(time_s):
            raise ValueError("prediction time must be finite")
        return self.intercept(path_id) + self.rate_hz_s * (time_s - self.reference_time_s)


@dataclass(frozen=True, slots=True)
class SeparatePathRateFit:
    """One independent robust line fitted to one receiver path."""

    path_id: str
    physical_radio_id: str
    reference_time_s: float
    intercept_hz: float
    rate_hz_s: float
    point_count: int
    residual_rms_hz: float
    residual_mad_hz: float
    iteration_count: int
    converged: bool
    fit_symbols: str = "even Qin only"
    odd_symbols_influenced_fit: bool = False

    def predict(self, time_s: float) -> float:
        if not math.isfinite(time_s):
            raise ValueError("prediction time must be finite")
        return self.intercept_hz + self.rate_hz_s * (time_s - self.reference_time_s)


@dataclass(frozen=True, slots=True)
class RadioRateFit:
    """One radio-specific slope with a free intercept for each receiver path."""

    physical_radio_id: str
    reference_time_s: float
    rate_hz_s: float
    path_intercepts_hz: tuple[tuple[str, float], ...]
    point_count: int
    path_count: int
    residual_rms_hz: float
    residual_mad_hz: float
    iteration_count: int
    converged: bool
    fit_symbols: str = "even Qin only"
    odd_symbols_influenced_fit: bool = False

    def intercept(self, path_id: str) -> float:
        for candidate, value in self.path_intercepts_hz:
            if candidate == path_id:
                return value
        raise ValueError(f"path is absent from radio-rate fit: {path_id}")

    def predict(self, path_id: str, time_s: float) -> float:
        if not math.isfinite(time_s):
            raise ValueError("prediction time must be finite")
        return self.intercept(path_id) + self.rate_hz_s * (time_s - self.reference_time_s)


@dataclass(frozen=True, slots=True)
class PredictionMetrics:
    """Error summary on one explicit held-out point mask."""

    point_count: int
    rms_hz: float
    median_absolute_hz: float
    mean_error_hz: float


@dataclass(frozen=True, slots=True)
class CausalPrediction:
    """One current odd-Qin response predicted from strictly past even Qin."""

    point_id: str
    path_id: str
    time_s: float
    prediction_hz: float
    odd_cfo_hz: float
    error_hz: float
    history_count: int
    history_start_s: float
    history_stop_s: float


def fit_common_rate(
    points: tuple[MultiRadioFramePoint, ...],
    *,
    huber_tuning: float = 1.345,
    maximum_iterations: int = 50,
    relative_tolerance: float = 1e-10,
) -> CommonRateFit:
    """Fit one Huber slope and free path intercepts using even Qin only."""

    ordered = _validate_points(points, minimum_paths=2)
    path_ids = tuple(sorted({point.path_id for point in ordered}))
    reference = float(np.mean([point.time_s for point in ordered]))
    design = np.zeros((len(ordered), len(path_ids) + 1), dtype=float)
    path_index = {path_id: index for index, path_id in enumerate(path_ids)}
    for row, point in enumerate(ordered):
        design[row, path_index[point.path_id]] = 1.0
        design[row, -1] = point.time_s - reference
    response = np.asarray([point.even_cfo_hz for point in ordered], dtype=float)
    coefficients, residual, iterations, converged = _huber_irls(
        design,
        response,
        huber_tuning=huber_tuning,
        maximum_iterations=maximum_iterations,
        relative_tolerance=relative_tolerance,
    )
    return CommonRateFit(
        reference_time_s=reference,
        rate_hz_s=float(coefficients[-1]),
        path_intercepts_hz=tuple(
            (path_id, float(coefficients[index])) for index, path_id in enumerate(path_ids)
        ),
        point_count=len(ordered),
        path_count=len(path_ids),
        residual_rms_hz=float(np.sqrt(np.mean(residual**2))),
        residual_mad_hz=float(np.median(np.abs(residual - np.median(residual)))),
        iteration_count=iterations,
        converged=converged,
    )


def fit_separate_path_rates(
    points: tuple[MultiRadioFramePoint, ...],
    *,
    huber_tuning: float = 1.345,
    maximum_iterations: int = 50,
    relative_tolerance: float = 1e-10,
) -> tuple[SeparatePathRateFit, ...]:
    """Fit one independent Huber line per path using the same even-Qin points."""

    ordered = _validate_points(points, minimum_paths=1)
    output = []
    for path_id in sorted({point.path_id for point in ordered}):
        selected = tuple(point for point in ordered if point.path_id == path_id)
        if len(selected) < 3:
            raise ValueError(f"path has fewer than three points: {path_id}")
        reference = float(np.mean([point.time_s for point in selected]))
        design = np.column_stack(
            (
                np.ones(len(selected), dtype=float),
                np.asarray([point.time_s - reference for point in selected], dtype=float),
            )
        )
        response = np.asarray([point.even_cfo_hz for point in selected], dtype=float)
        coefficients, residual, iterations, converged = _huber_irls(
            design,
            response,
            huber_tuning=huber_tuning,
            maximum_iterations=maximum_iterations,
            relative_tolerance=relative_tolerance,
        )
        radios = {point.physical_radio_id for point in selected}
        if len(radios) != 1:
            raise ValueError("one path maps to multiple physical radios")
        output.append(
            SeparatePathRateFit(
                path_id=path_id,
                physical_radio_id=next(iter(radios)),
                reference_time_s=reference,
                intercept_hz=float(coefficients[0]),
                rate_hz_s=float(coefficients[1]),
                point_count=len(selected),
                residual_rms_hz=float(np.sqrt(np.mean(residual**2))),
                residual_mad_hz=float(np.median(np.abs(residual - np.median(residual)))),
                iteration_count=iterations,
                converged=converged,
            )
        )
    return tuple(output)


def fit_radio_rates(
    points: tuple[MultiRadioFramePoint, ...],
    *,
    huber_tuning: float = 1.345,
    maximum_iterations: int = 50,
    relative_tolerance: float = 1e-10,
) -> tuple[RadioRateFit, ...]:
    """Fit one robust slope per physical radio with free receiver-path offsets."""

    ordered = _validate_points(points, minimum_paths=1)
    output = []
    for radio_id in sorted({point.physical_radio_id for point in ordered}):
        selected = tuple(point for point in ordered if point.physical_radio_id == radio_id)
        path_ids = tuple(sorted({point.path_id for point in selected}))
        reference = float(np.mean([point.time_s for point in selected]))
        design = np.zeros((len(selected), len(path_ids) + 1), dtype=float)
        path_index = {path_id: index for index, path_id in enumerate(path_ids)}
        for row, point in enumerate(selected):
            design[row, path_index[point.path_id]] = 1.0
            design[row, -1] = point.time_s - reference
        response = np.asarray([point.even_cfo_hz for point in selected], dtype=float)
        coefficients, residual, iterations, converged = _huber_irls(
            design,
            response,
            huber_tuning=huber_tuning,
            maximum_iterations=maximum_iterations,
            relative_tolerance=relative_tolerance,
        )
        output.append(
            RadioRateFit(
                physical_radio_id=radio_id,
                reference_time_s=reference,
                rate_hz_s=float(coefficients[-1]),
                path_intercepts_hz=tuple(
                    (path_id, float(coefficients[index])) for index, path_id in enumerate(path_ids)
                ),
                point_count=len(selected),
                path_count=len(path_ids),
                residual_rms_hz=float(np.sqrt(np.mean(residual**2))),
                residual_mad_hz=float(np.median(np.abs(residual - np.median(residual)))),
                iteration_count=iterations,
                converged=converged,
            )
        )
    return tuple(output)


def common_rate_prediction_metrics(
    fit: CommonRateFit,
    points: tuple[MultiRadioFramePoint, ...],
) -> PredictionMetrics:
    """Score one shared fit against odd Qin on the supplied explicit mask."""

    checked = _validate_prediction_points(points)
    errors = np.asarray(
        [_required_odd(point) - fit.predict(point.path_id, point.time_s) for point in checked]
    )
    return _metrics(errors)


def separate_rate_prediction_metrics(
    fits: tuple[SeparatePathRateFit, ...],
    points: tuple[MultiRadioFramePoint, ...],
) -> PredictionMetrics:
    """Score path-local fits against odd Qin on the supplied explicit mask."""

    checked = _validate_prediction_points(points)
    by_path = {fit.path_id: fit for fit in fits}
    if len(by_path) != len(fits):
        raise ValueError("separate path fits contain a duplicate")
    errors = []
    for point in checked:
        fit = by_path.get(point.path_id)
        if fit is None:
            raise ValueError(f"held-out path is absent from separate fits: {point.path_id}")
        errors.append(_required_odd(point) - fit.predict(point.time_s))
    return _metrics(np.asarray(errors, dtype=float))


def radio_rate_prediction_metrics(
    fits: tuple[RadioRateFit, ...],
    points: tuple[MultiRadioFramePoint, ...],
) -> PredictionMetrics:
    """Score physical-radio fits against odd Qin on the supplied explicit mask."""

    checked = _validate_prediction_points(points)
    by_radio = {fit.physical_radio_id: fit for fit in fits}
    if len(by_radio) != len(fits):
        raise ValueError("radio fits contain a duplicate")
    errors = []
    for point in checked:
        fit = by_radio.get(point.physical_radio_id)
        if fit is None:
            raise ValueError(f"held-out radio is absent from fits: {point.physical_radio_id}")
        errors.append(_required_odd(point) - fit.predict(point.path_id, point.time_s))
    return _metrics(np.asarray(errors, dtype=float))


def fixed_history_causal_predictions(
    all_points: tuple[MultiRadioFramePoint, ...],
    targets: tuple[MultiRadioFramePoint, ...],
    *,
    history_s: float = 0.5,
    minimum_history_frames: int = 20,
) -> tuple[CausalPrediction, ...]:
    """Predict current odd Qin from a strict past-only, fixed-length even history."""

    ordered = _validate_points(all_points, minimum_paths=1)
    selected_targets = _validate_prediction_points(targets)
    if not math.isfinite(history_s) or history_s <= 0.0:
        raise ValueError("causal history must be finite and positive")
    if minimum_history_frames < 3:
        raise ValueError("causal history requires at least three frames")
    by_path: dict[str, list[MultiRadioFramePoint]] = {}
    for point in ordered:
        by_path.setdefault(point.path_id, []).append(point)
    output = []
    for target in selected_targets:
        history = tuple(
            point
            for point in by_path.get(target.path_id, ())
            if target.time_s - history_s <= point.time_s < target.time_s
        )
        if len(history) < minimum_history_frames:
            continue
        fit = fit_separate_path_rates(history)[0]
        prediction = fit.predict(target.time_s)
        output.append(
            CausalPrediction(
                point_id=target.point_id,
                path_id=target.path_id,
                time_s=target.time_s,
                prediction_hz=prediction,
                odd_cfo_hz=_required_odd(target),
                error_hz=_required_odd(target) - prediction,
                history_count=len(history),
                history_start_s=min(point.time_s for point in history),
                history_stop_s=max(point.time_s for point in history),
            )
        )
    return tuple(output)


def prediction_metrics_from_causal(
    predictions: tuple[CausalPrediction, ...],
) -> PredictionMetrics:
    """Summarize one nonempty collection of causal prediction errors."""

    if not predictions or len({item.point_id for item in predictions}) != len(predictions):
        raise ValueError("causal predictions must be nonempty and uniquely identified")
    return _metrics(np.asarray([item.error_hz for item in predictions], dtype=float))


def block_bootstrap_rate_sigma(
    points: tuple[MultiRadioFramePoint, ...],
    *,
    shared: bool,
    block_width_s: float = 0.05,
    replicates: int = 500,
    seed: int = 418_050,
) -> float:
    """Return deterministic pairs-block-bootstrap slope standard deviation."""

    ordered = _validate_points(points, minimum_paths=2 if shared else 1)

    def estimator(sample: tuple[MultiRadioFramePoint, ...]) -> float:
        if shared:
            return fit_common_rate(sample).rate_hz_s
        fits = fit_separate_path_rates(sample)
        if len(fits) != 1:
            raise ValueError("non-shared bootstrap requires one path")
        return fits[0].rate_hz_s

    return _block_bootstrap_sigma(
        ordered,
        estimator=estimator,
        block_width_s=block_width_s,
        replicates=replicates,
        seed=seed,
    )


def block_bootstrap_radio_rate_sigma(
    points: tuple[MultiRadioFramePoint, ...],
    *,
    block_width_s: float = 0.05,
    replicates: int = 500,
    seed: int = 418_050,
) -> float:
    """Return the block-bootstrap slope sigma for exactly one physical radio."""

    ordered = _validate_points(points, minimum_paths=1)
    if len({point.physical_radio_id for point in ordered}) != 1:
        raise ValueError("radio bootstrap requires exactly one physical radio")

    def estimator(sample: tuple[MultiRadioFramePoint, ...]) -> float:
        fits = fit_radio_rates(sample)
        if len(fits) != 1:
            raise ValueError("radio bootstrap sample changed radio identity")
        return fits[0].rate_hz_s

    return _block_bootstrap_sigma(
        ordered,
        estimator=estimator,
        block_width_s=block_width_s,
        replicates=replicates,
        seed=seed,
    )


def _block_bootstrap_sigma(
    ordered: tuple[MultiRadioFramePoint, ...],
    *,
    estimator: Callable[[tuple[MultiRadioFramePoint, ...]], float],
    block_width_s: float,
    replicates: int,
    seed: int,
) -> float:
    if not math.isfinite(block_width_s) or block_width_s <= 0.0:
        raise ValueError("bootstrap block width must be finite and positive")
    if replicates < 20 or seed < 0:
        raise ValueError("bootstrap count or seed is unsupported")
    origin = min(point.time_s for point in ordered)
    blocks: dict[int, tuple[MultiRadioFramePoint, ...]] = {}
    for point in ordered:
        index = math.floor((point.time_s - origin) / block_width_s + 1e-12)
        blocks.setdefault(index, tuple())
        blocks[index] = (*blocks[index], point)
    block_values = tuple(blocks[index] for index in sorted(blocks))
    if len(block_values) < 3:
        raise ValueError("bootstrap requires at least three time blocks")
    generator = np.random.default_rng(seed)
    rates: list[float] = []
    attempts = 0
    maximum_attempts = 10 * replicates
    while len(rates) < replicates and attempts < maximum_attempts:
        attempts += 1
        indexes = generator.integers(0, len(block_values), size=len(block_values))
        selected = tuple(point for index in indexes for point in block_values[int(index)])
        sample = tuple(
            MultiRadioFramePoint(
                point_id=f"bootstrap-{attempts}-{ordinal}-{point.point_id}",
                path_id=point.path_id,
                physical_radio_id=point.physical_radio_id,
                time_s=point.time_s,
                even_cfo_hz=point.even_cfo_hz,
                odd_cfo_hz=point.odd_cfo_hz,
                even_sigma_hz=point.even_sigma_hz,
            )
            for ordinal, point in enumerate(selected)
        )
        try:
            rates.append(float(estimator(sample)))
        except (ValueError, np.linalg.LinAlgError):
            continue
    if len(rates) != replicates:
        raise ValueError("bootstrap could not produce the frozen replicate count")
    return float(np.std(np.asarray(rates, dtype=float), ddof=1))


def _validate_points(
    points: tuple[MultiRadioFramePoint, ...],
    *,
    minimum_paths: int,
) -> tuple[MultiRadioFramePoint, ...]:
    if len(points) < 3 or len({point.point_id for point in points}) != len(points):
        raise ValueError("rate points must contain at least three unique observations")
    ordered = tuple(sorted(points, key=lambda point: (point.time_s, point.path_id, point.point_id)))
    paths = {point.path_id for point in ordered}
    if len(paths) < minimum_paths:
        raise ValueError("rate points do not span the required path count")
    for path_id in paths:
        selected = [point for point in ordered if point.path_id == path_id]
        if len(selected) < 3 or len({point.time_s for point in selected}) < 2:
            raise ValueError(f"path lacks identifiable time support: {path_id}")
        if len({point.physical_radio_id for point in selected}) != 1:
            raise ValueError(f"path maps to multiple physical radios: {path_id}")
    return ordered


def _validate_prediction_points(
    points: tuple[MultiRadioFramePoint, ...],
) -> tuple[MultiRadioFramePoint, ...]:
    if not points or len({point.point_id for point in points}) != len(points):
        raise ValueError("prediction points must be nonempty and uniquely identified")
    if any(point.odd_cfo_hz is None for point in points):
        raise ValueError("prediction points require an odd-Qin response")
    return tuple(sorted(points, key=lambda point: (point.time_s, point.path_id, point.point_id)))


def _required_odd(point: MultiRadioFramePoint) -> float:
    """Return a validated odd-Qin response with static type narrowing."""

    if point.odd_cfo_hz is None:
        raise ValueError("prediction point requires an odd-Qin response")
    return point.odd_cfo_hz


def _huber_irls(
    design: np.ndarray,
    response: np.ndarray,
    *,
    huber_tuning: float,
    maximum_iterations: int,
    relative_tolerance: float,
) -> tuple[np.ndarray, np.ndarray, int, bool]:
    if (
        not math.isfinite(huber_tuning)
        or huber_tuning <= 0.0
        or maximum_iterations < 1
        or not math.isfinite(relative_tolerance)
        or relative_tolerance <= 0.0
    ):
        raise ValueError("Huber settings are invalid")
    if design.ndim != 2 or response.shape != (design.shape[0],):
        raise ValueError("regression arrays have incompatible shapes")
    if design.shape[0] <= design.shape[1] or np.linalg.matrix_rank(design) < design.shape[1]:
        raise ValueError("rate design matrix is not identifiable")
    coefficients = np.linalg.lstsq(design, response, rcond=None)[0]
    converged = False
    _iteration = 0
    for _iteration in range(1, maximum_iterations + 1):
        residual = response - design @ coefficients
        center = float(np.median(residual))
        scale = 1.4826 * float(np.median(np.abs(residual - center)))
        scale = max(scale, np.finfo(float).eps * max(1.0, float(np.max(np.abs(response)))))
        standardized = np.abs(residual - center) / (huber_tuning * scale)
        weights = np.ones_like(standardized)
        outside = standardized > 1.0
        weights[outside] = 1.0 / standardized[outside]
        weighted_design = design * np.sqrt(weights)[:, None]
        weighted_response = response * np.sqrt(weights)
        updated = np.linalg.lstsq(weighted_design, weighted_response, rcond=None)[0]
        scale_coefficient = max(1.0, float(np.linalg.norm(coefficients)))
        if float(np.linalg.norm(updated - coefficients)) <= relative_tolerance * scale_coefficient:
            coefficients = updated
            converged = True
            break
        coefficients = updated
    residual = response - design @ coefficients
    return coefficients, residual, _iteration, converged


def _metrics(errors: np.ndarray) -> PredictionMetrics:
    if errors.ndim != 1 or errors.size == 0 or not np.all(np.isfinite(errors)):
        raise ValueError("prediction errors must be one nonempty finite vector")
    return PredictionMetrics(
        point_count=int(errors.size),
        rms_hz=float(np.sqrt(np.mean(errors**2))),
        median_absolute_hz=float(np.median(np.abs(errors))),
        mean_error_hz=float(np.mean(errors)),
    )
