"""Pure held-out matching of reset-debiased ramp rates to TLE rate curves.

The radio observable is a collection of short, frequency-continuous ramp
slopes.  It has no trustworthy absolute CFO intercept, and an unknown receiver
or transmitter frequency drift can add a nearly constant rate.  Candidate
satellites are therefore compared in *rate space* after fitting one bounded
constant rate nuisance on the chronological training ramps.  Satellite identity
and nuisance are selected without looking at the held-out tail.

This module deliberately knows nothing about recordings, TLE archives, SGP4,
files, or reports.  Callers provide the predicted Doppler rate at the same ramp
times as the observations.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class RampRateSeries:
    """Independent local ramp-rate measurements from one radio trajectory."""

    time_s: tuple[float, ...]
    rate_hz_s: tuple[float, ...]
    sigma_hz_s: tuple[float, ...]

    def __post_init__(self) -> None:
        count = len(self.time_s)
        if count < 5 or len(self.rate_hz_s) != count or len(self.sigma_hz_s) != count:
            raise ValueError("ramp-rate series needs at least five equal-length samples")
        times = np.asarray(self.time_s, dtype=float)
        values = np.asarray((*self.rate_hz_s, *self.sigma_hz_s), dtype=float)
        if not np.isfinite(times).all() or not np.isfinite(values).all():
            raise ValueError("ramp-rate series must be finite")
        if np.any(np.diff(times) <= 0.0):
            raise ValueError("ramp-rate times must be strictly increasing")
        if any(value <= 0.0 for value in self.sigma_hz_s):
            raise ValueError("ramp-rate uncertainty must be positive")


@dataclass(frozen=True, slots=True)
class CandidateRateSeries:
    """One satellite's predicted geometric Doppler rate at the ramp times."""

    object_name: str
    catalog_number: int
    predicted_rate_hz_s: tuple[float, ...]
    peak_elevation_deg: float
    minimum_elevation_deg: float
    element_epoch_utc_ns: int
    element_age_s: float

    def __post_init__(self) -> None:
        if not self.object_name or self.catalog_number <= 0:
            raise ValueError("candidate identity is incomplete")
        values = (
            *self.predicted_rate_hz_s,
            self.peak_elevation_deg,
            self.minimum_elevation_deg,
            self.element_age_s,
        )
        if not self.predicted_rate_hz_s or any(not math.isfinite(value) for value in values):
            raise ValueError("candidate rate series must be finite")


@dataclass(frozen=True, slots=True)
class RampRateAssociationConfig:
    """Numerical controls; thresholds are not claims of satellite identity."""

    training_fraction: float = 0.60
    nuisance_rate_bound_hz_s: float = 200.0
    uncertainty_floor_hz_s: float = 100.0
    huber_k: float = 1.345
    maximum_iterations: int = 50

    def __post_init__(self) -> None:
        if not 0.0 < self.training_fraction < 1.0:
            raise ValueError("training fraction must lie in (0, 1)")
        values = (
            self.nuisance_rate_bound_hz_s,
            self.uncertainty_floor_hz_s,
            self.huber_k,
        )
        if any(not math.isfinite(value) or value <= 0.0 for value in values):
            raise ValueError("association scales and bounds must be finite and positive")
        if self.maximum_iterations < 1:
            raise ValueError("maximum iterations must be positive")


@dataclass(frozen=True, slots=True)
class RateFitMetrics:
    fitted_rate_nuisance_hz_s: float
    nuisance_at_bound: bool
    train_rms_hz_s: float
    holdout_rms_hz_s: float
    full_rms_hz_s: float
    train_standardized_rms: float
    holdout_standardized_rms: float
    full_standardized_rms: float
    train_median_absolute_hz_s: float
    holdout_median_absolute_hz_s: float


@dataclass(frozen=True, slots=True)
class RankedRateAssociation:
    rank: int
    candidate: CandidateRateSeries
    metrics: RateFitMetrics


@dataclass(frozen=True, slots=True)
class RampRateAssociationResult:
    candidate_count: int
    training_indices: tuple[int, ...]
    holdout_indices: tuple[int, ...]
    constant_rate_null: RateFitMetrics
    affine_rate_null: RateFitMetrics
    affine_rate_progression_hz_s2: float
    ranked: tuple[RankedRateAssociation, ...]
    runner_up_train_standardized_margin: float | None


def _split(count: int, fraction: float) -> np.ndarray:
    cutoff = int(np.clip(math.ceil(fraction * count), 3, count - 2))
    selected = np.zeros(count, dtype=bool)
    selected[:cutoff] = True
    return selected


def _metrics(
    residual: np.ndarray,
    sigma: np.ndarray,
    train: np.ndarray,
    *,
    nuisance: float,
    bound: float,
) -> RateFitMetrics:
    def rms(values: np.ndarray) -> float:
        return float(np.sqrt(np.mean(values**2)))

    return RateFitMetrics(
        fitted_rate_nuisance_hz_s=float(nuisance),
        nuisance_at_bound=math.isclose(abs(nuisance), bound, rel_tol=0.0, abs_tol=1e-8),
        train_rms_hz_s=rms(residual[train]),
        holdout_rms_hz_s=rms(residual[~train]),
        full_rms_hz_s=rms(residual),
        train_standardized_rms=rms(residual[train] / sigma[train]),
        holdout_standardized_rms=rms(residual[~train] / sigma[~train]),
        full_standardized_rms=rms(residual / sigma),
        train_median_absolute_hz_s=float(np.median(np.abs(residual[train]))),
        holdout_median_absolute_hz_s=float(np.median(np.abs(residual[~train]))),
    )


def _fit_bounded_location(
    raw_residual: np.ndarray,
    sigma: np.ndarray,
    train: np.ndarray,
    config: RampRateAssociationConfig,
) -> tuple[np.ndarray, RateFitMetrics]:
    base_weights = 1.0 / sigma**2
    nuisance = float(
        np.clip(
            np.average(raw_residual[train], weights=base_weights[train]),
            -config.nuisance_rate_bound_hz_s,
            config.nuisance_rate_bound_hz_s,
        )
    )
    for _iteration in range(config.maximum_iterations):
        residual = raw_residual - nuisance
        center = float(np.median(residual[train]))
        scale = max(
            1.0,
            float(np.median(sigma[train])),
            1.4826 * float(np.median(np.abs(residual[train] - center))),
        )
        normalized = np.abs(residual) / (config.huber_k * scale)
        huber = np.ones(raw_residual.size, dtype=float)
        tail = normalized > 1.0
        huber[tail] = 1.0 / normalized[tail]
        weights = base_weights * huber
        updated = float(
            np.clip(
                np.average(raw_residual[train], weights=weights[train]),
                -config.nuisance_rate_bound_hz_s,
                config.nuisance_rate_bound_hz_s,
            )
        )
        if abs(updated - nuisance) < 1e-8:
            nuisance = updated
            break
        nuisance = updated
    residual = raw_residual - nuisance
    return residual, _metrics(
        residual,
        sigma,
        train,
        nuisance=nuisance,
        bound=config.nuisance_rate_bound_hz_s,
    )


def _fit_affine_null(
    times: np.ndarray,
    observed: np.ndarray,
    sigma: np.ndarray,
    train: np.ndarray,
    config: RampRateAssociationConfig,
) -> tuple[float, RateFitMetrics]:
    reference = float(np.mean(times[train]))
    design = np.column_stack((np.ones(times.size), times - reference))
    weights = 1.0 / sigma**2
    coefficients = np.linalg.lstsq(
        design[train] * np.sqrt(weights[train, None]),
        observed[train] * np.sqrt(weights[train]),
        rcond=None,
    )[0]
    for _iteration in range(config.maximum_iterations):
        residual = observed - design @ coefficients
        center = float(np.median(residual[train]))
        scale = max(
            1.0,
            float(np.median(sigma[train])),
            1.4826 * float(np.median(np.abs(residual[train] - center))),
        )
        normalized = np.abs(residual) / (config.huber_k * scale)
        huber = np.ones(observed.size, dtype=float)
        tail = normalized > 1.0
        huber[tail] = 1.0 / normalized[tail]
        effective = weights * huber
        root = np.sqrt(effective[train])
        updated = np.linalg.lstsq(
            design[train] * root[:, None], observed[train] * root, rcond=None
        )[0]
        if float(np.max(np.abs(updated - coefficients))) < 1e-8:
            coefficients = updated
            break
        coefficients = updated
    residual = observed - design @ coefficients
    # The generic field holds the fitted rate level for the radio-only null.
    metrics = _metrics(
        residual,
        sigma,
        train,
        nuisance=float(coefficients[0]),
        bound=math.inf,
    )
    return float(coefficients[1]), metrics


def associate_ramp_rates(
    observed: RampRateSeries,
    candidates: tuple[CandidateRateSeries, ...],
    config: RampRateAssociationConfig | None = None,
    *,
    limit: int = 10,
) -> RampRateAssociationResult:
    """Rank candidates on early ramps and report the untouched late-ramp fit."""

    if limit < 1:
        raise ValueError("association ranking limit must be positive")
    if config is None:
        config = RampRateAssociationConfig()
    times = np.asarray(observed.time_s, dtype=float)
    rates = np.asarray(observed.rate_hz_s, dtype=float)
    sigma = np.maximum(np.asarray(observed.sigma_hz_s, dtype=float), config.uncertainty_floor_hz_s)
    train = _split(times.size, config.training_fraction)

    _constant_residual, constant = _fit_bounded_location(
        rates,
        sigma,
        train,
        RampRateAssociationConfig(
            training_fraction=config.training_fraction,
            nuisance_rate_bound_hz_s=max(1.0, float(np.max(np.abs(rates))) * 2.0),
            uncertainty_floor_hz_s=config.uncertainty_floor_hz_s,
            huber_k=config.huber_k,
            maximum_iterations=config.maximum_iterations,
        ),
    )
    progression, affine = _fit_affine_null(times, rates, sigma, train, config)

    evaluated: list[tuple[CandidateRateSeries, RateFitMetrics]] = []
    for candidate in candidates:
        predicted = np.asarray(candidate.predicted_rate_hz_s, dtype=float)
        if predicted.shape != rates.shape:
            raise ValueError("candidate rate count differs from observed ramp count")
        _residual, metrics = _fit_bounded_location(rates - predicted, sigma, train, config)
        evaluated.append((candidate, metrics))
    evaluated.sort(
        key=lambda item: (
            item[1].train_standardized_rms,
            item[0].catalog_number,
        )
    )
    ranked = tuple(
        RankedRateAssociation(rank=index, candidate=item[0], metrics=item[1])
        for index, item in enumerate(evaluated[:limit], start=1)
    )
    margin = (
        evaluated[1][1].train_standardized_rms - evaluated[0][1].train_standardized_rms
        if len(evaluated) > 1
        else None
    )
    return RampRateAssociationResult(
        candidate_count=len(evaluated),
        training_indices=tuple(int(index) for index in np.flatnonzero(train)),
        holdout_indices=tuple(int(index) for index in np.flatnonzero(~train)),
        constant_rate_null=constant,
        affine_rate_null=affine,
        affine_rate_progression_hz_s2=progression,
        ranked=ranked,
        runner_up_train_standardized_margin=margin,
    )
