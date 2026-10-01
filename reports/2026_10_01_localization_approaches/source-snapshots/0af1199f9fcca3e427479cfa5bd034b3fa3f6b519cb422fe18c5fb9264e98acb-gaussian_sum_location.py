"""Pure bounded Gaussian-sum update for single-scan localization research.

The state is deliberately generic.  Position, clock, receiver drift, and other
persistent shared nuisances are simply coordinates in the same Gaussian state.
Prediction callbacks provide a local linearization for one whole observation
factor; track-local Gaussian nuisances should be marginalized into its noise
covariance with :func:`marginalize_local_covariance`.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from math import log, pi

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]
Prior = float | Callable[[FloatArray], float]
Predictor = Callable[[FloatArray], "Prediction"]


def _array(value: object, *, ndim: int, name: str) -> FloatArray:
    result = np.array(value, dtype=np.float64, copy=True)
    if result.ndim != ndim or not np.all(np.isfinite(result)):
        raise ValueError(f"{name} must be a finite {ndim}-dimensional array")
    result.setflags(write=False)
    return result


def _spd(value: object, *, dimension: int, name: str) -> FloatArray:
    result = _array(value, ndim=2, name=name)
    if result.shape != (dimension, dimension):
        raise ValueError(f"{name} has shape {result.shape}, expected {(dimension, dimension)}")
    if not np.allclose(result, result.T, rtol=1e-10, atol=1e-12):
        raise ValueError(f"{name} must be symmetric")
    try:
        np.linalg.cholesky(result)
    except np.linalg.LinAlgError as error:
        raise ValueError(f"{name} must be positive definite") from error
    return result


def _symmetrize_constructed(value: FloatArray) -> FloatArray:
    """Remove floating skew from an algebraically symmetric internal expression."""
    return (value + value.T) * 0.5


@dataclass(frozen=True)
class GaussianComponent:
    weight: float
    mean: FloatArray
    covariance: FloatArray
    identity_history: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        mean = _array(self.mean, ndim=1, name="mean")
        covariance = _spd(self.covariance, dimension=mean.size, name="covariance")
        if not np.isfinite(self.weight) or self.weight <= 0.0:
            raise ValueError("component weight must be finite and positive")
        object.__setattr__(self, "mean", mean)
        object.__setattr__(self, "covariance", covariance)
        object.__setattr__(self, "identity_history", tuple(self.identity_history))


@dataclass(frozen=True)
class Prediction:
    mean: FloatArray
    jacobian: FloatArray
    covariance: FloatArray
    eligible: bool = True

    def __post_init__(self) -> None:
        mean = _array(self.mean, ndim=1, name="prediction mean")
        jacobian = _array(self.jacobian, ndim=2, name="prediction Jacobian")
        if jacobian.shape[0] != mean.size:
            raise ValueError("prediction Jacobian row count must match prediction dimension")
        covariance = _spd(self.covariance, dimension=mean.size, name="prediction covariance")
        object.__setattr__(self, "mean", mean)
        object.__setattr__(self, "jacobian", jacobian)
        object.__setattr__(self, "covariance", covariance)


@dataclass(frozen=True)
class Candidate:
    label: str
    prior: Prior
    predict: Predictor
    prior_is_local: bool = True

    def __post_init__(self) -> None:
        if not self.label or self.label == "background":
            raise ValueError("candidate label must be non-empty and differ from 'background'")
        if callable(self.prior) and not self.prior_is_local:
            raise ValueError("a state-dependent prior must declare prior_is_local=True")


@dataclass(frozen=True)
class ObservationFactor:
    observation_ids: tuple[str, ...]
    observation: FloatArray
    candidates: tuple[Candidate, ...]
    background_prior: Prior
    background_log_likelihood: float

    def __post_init__(self) -> None:
        ids = tuple(self.observation_ids)
        observation = _array(self.observation, ndim=1, name="observation")
        candidates = tuple(self.candidates)
        if not ids or any(not item for item in ids) or len(set(ids)) != len(ids):
            raise ValueError("observation_ids must be non-empty and unique")
        if observation.size == 0:
            raise ValueError("observation must be non-empty")
        labels = [candidate.label for candidate in candidates]
        if not candidates or len(set(labels)) != len(labels):
            raise ValueError("candidates must be non-empty with unique labels")
        if callable(self.background_prior):
            pass
        elif not np.isfinite(self.background_prior):
            raise ValueError("background prior must be finite")
        if not np.isfinite(self.background_log_likelihood):
            raise ValueError("background log likelihood must be finite")
        object.__setattr__(self, "observation_ids", ids)
        object.__setattr__(self, "observation", observation)
        object.__setattr__(self, "candidates", candidates)


@dataclass(frozen=True)
class FilterConfig:
    max_components: int
    min_weight: float = 0.0
    greedy: bool = False
    max_child_work: int = 4096

    def __post_init__(self) -> None:
        if self.max_components < 1 or self.max_child_work < 1:
            raise ValueError("component and child-work limits must be positive")
        if not np.isfinite(self.min_weight) or not 0.0 <= self.min_weight < 1.0:
            raise ValueError("min_weight must be finite and in [0, 1)")


@dataclass(frozen=True)
class FilterState:
    components: tuple[GaussianComponent, ...]
    consumed_observation_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        components = tuple(self.components)
        consumed = tuple(self.consumed_observation_ids)
        if not components:
            raise ValueError("filter state must contain at least one component")
        dimensions = {component.mean.size for component in components}
        if len(dimensions) != 1:
            raise ValueError("all components must have the same state dimension")
        if len(set(consumed)) != len(consumed):
            raise ValueError("consumed observation IDs must be unique")
        total = sum(component.weight for component in components)
        if not np.isclose(total, 1.0, rtol=1e-10, atol=1e-12):
            raise ValueError("component weights must sum to one")
        object.__setattr__(self, "components", components)
        object.__setattr__(self, "consumed_observation_ids", consumed)


@dataclass(frozen=True)
class UpdateResult:
    state: FilterState
    predictive_log_density: float
    association_probabilities: dict[str, float]
    background_probability: float
    retained_pre_normalization_mass: float
    discarded_pre_normalization_mass: float
    status: str
    flags: tuple[str, ...]


@dataclass(frozen=True)
class _Child:
    log_weight: float
    parent: GaussianComponent
    prediction: Prediction | None
    label: str


def gaussian_logpdf(residual: object, covariance: object) -> float:
    """Return the proper multivariate-normal log density using Cholesky solves."""
    residual_array = _array(residual, ndim=1, name="residual")
    covariance_array = _spd(covariance, dimension=residual_array.size, name="covariance")
    chol = np.linalg.cholesky(covariance_array)
    solved = np.linalg.solve(chol, residual_array)
    return float(
        -0.5
        * (
            residual_array.size * log(2.0 * pi)
            + 2.0 * np.log(np.diag(chol)).sum()
            + solved @ solved
        )
    )


def marginalize_local_covariance(
    measurement_covariance: object,
    local_design: object,
    local_prior_covariance: object,
) -> FloatArray:
    """Integrate a zero-mean track-local Gaussian offset out of a factor."""
    measurement_array = _array(measurement_covariance, ndim=2, name="measurement covariance")
    if measurement_array.shape[0] != measurement_array.shape[1]:
        raise ValueError("measurement covariance must be square")
    if not np.allclose(measurement_array, measurement_array.T, rtol=1e-10, atol=1e-12):
        raise ValueError("measurement covariance must be symmetric")
    measurement = measurement_array
    design = _array(local_design, ndim=2, name="local design")
    if design.shape[0] != measurement.shape[0]:
        raise ValueError("local design row count must match the observation dimension")
    local = _spd(local_prior_covariance, dimension=design.shape[1], name="local prior covariance")
    return _spd(
        _symmetrize_constructed(measurement + design @ local @ design.T),
        dimension=measurement.shape[0],
        name="marginal covariance",
    )


def _prior_value(prior: Prior, mean: FloatArray, name: str) -> float:
    value = prior(mean) if callable(prior) else prior
    value = float(value)
    if not np.isfinite(value) or value < 0.0:
        raise ValueError(f"{name} prior must be finite and non-negative")
    return value


def _logsumexp(values: Sequence[float]) -> float:
    maximum = max(values)
    if not np.isfinite(maximum):
        raise ValueError("factor has zero predictive density")
    return maximum + log(sum(np.exp(value - maximum) for value in values))


def _condition(
    parent: GaussianComponent, prediction: Prediction, observation: FloatArray
) -> tuple[float, FloatArray, FloatArray]:
    if prediction.mean.shape != observation.shape:
        raise ValueError("prediction and observation dimensions differ")
    if prediction.jacobian.shape[1] != parent.mean.size:
        raise ValueError("prediction Jacobian column count must match state dimension")
    h = prediction.jacobian
    p = parent.covariance
    innovation_covariance = _spd(
        _symmetrize_constructed(h @ p @ h.T + prediction.covariance),
        dimension=observation.size,
        name="innovation covariance",
    )
    residual = observation - prediction.mean
    cross_covariance = p @ h.T
    gain = np.linalg.solve(innovation_covariance, cross_covariance.T).T
    mean = parent.mean + gain @ residual
    covariance = p - gain @ cross_covariance.T
    covariance = (covariance + covariance.T) * 0.5
    return gaussian_logpdf(residual, innovation_covariance), mean, covariance


def _predictive_log_density(
    parent: GaussianComponent, prediction: Prediction, observation: FloatArray
) -> float:
    """Score without constructing a state-sized posterior covariance."""
    if prediction.mean.shape != observation.shape:
        raise ValueError("prediction and observation dimensions differ")
    if prediction.jacobian.shape[1] != parent.mean.size:
        raise ValueError("prediction Jacobian column count must match state dimension")
    active = np.flatnonzero(np.any(prediction.jacobian != 0.0, axis=0))
    if active.size:
        h = prediction.jacobian[:, active]
        covariance = parent.covariance[np.ix_(active, active)]
        projected = h @ covariance @ h.T
    else:
        projected = np.zeros_like(prediction.covariance)
    innovation_covariance = _spd(
        _symmetrize_constructed(projected + prediction.covariance),
        dimension=observation.size,
        name="innovation covariance",
    )
    return gaussian_logpdf(observation - prediction.mean, innovation_covariance)


def update_filter(
    state: FilterState, factor: ObservationFactor, config: FilterConfig
) -> UpdateResult:
    """Branch, score, condition, globally normalize, and bound one factor update."""
    duplicates = set(state.consumed_observation_ids).intersection(factor.observation_ids)
    if duplicates:
        raise ValueError(f"observation IDs already consumed: {sorted(duplicates)!r}")
    child_work = len(state.components) * (len(factor.candidates) + 1)
    if child_work > config.max_child_work:
        raise ValueError(
            f"factor requires {child_work} child evaluations, limit is {config.max_child_work}"
        )

    children: list[_Child] = []
    ineligible_positive_prior = False
    local_prior = callable(factor.background_prior) or any(
        callable(candidate.prior) for candidate in factor.candidates
    )
    for parent in state.components:
        background_prior = _prior_value(factor.background_prior, parent.mean, "background")
        candidate_priors = [
            _prior_value(candidate.prior, parent.mean, candidate.label)
            for candidate in factor.candidates
        ]
        if not np.isclose(background_prior + sum(candidate_priors), 1.0, rtol=1e-9, atol=1e-12):
            raise ValueError("source priors must sum to one at every component mean")
        if background_prior > 0.0:
            children.append(
                _Child(
                    log(parent.weight) + log(background_prior) + factor.background_log_likelihood,
                    parent,
                    None,
                    "background",
                )
            )
        for candidate, prior in zip(factor.candidates, candidate_priors, strict=True):
            if prior == 0.0:
                continue
            prediction = candidate.predict(parent.mean)
            if not prediction.eligible:
                ineligible_positive_prior = True
                continue
            likelihood = _predictive_log_density(parent, prediction, factor.observation)
            children.append(
                _Child(
                    log(parent.weight) + log(prior) + likelihood,
                    parent,
                    prediction,
                    candidate.label,
                )
            )
    if not children:
        raise ValueError("factor has no eligible branch with positive prior")

    predictive_log_density = _logsumexp([child.log_weight for child in children])
    probabilities = np.array(
        [np.exp(child.log_weight - predictive_log_density) for child in children], dtype=np.float64
    )
    association: dict[str, float] = {candidate.label: 0.0 for candidate in factor.candidates}
    background_probability = 0.0
    for child, probability in zip(children, probabilities, strict=True):
        if child.label == "background":
            background_probability += float(probability)
        else:
            association[child.label] += float(probability)

    order = sorted(
        range(len(children)),
        key=lambda index: (
            -probabilities[index],
            children[index].parent.identity_history + (children[index].label,),
        ),
    )
    limit = 1 if config.greedy else config.max_components
    retained_indices = [
        index
        for index in order
        if probabilities[index] > 0.0 and probabilities[index] >= config.min_weight
    ][:limit]
    if not retained_indices:
        retained_indices = order[:1]
    retained_mass = float(probabilities[retained_indices].sum())
    discarded_mass = float(max(0.0, 1.0 - retained_mass))
    materialized = []
    for index in retained_indices:
        child = children[index]
        if child.prediction is None:
            mean, covariance = child.parent.mean, child.parent.covariance
        else:
            _, mean, covariance = _condition(child.parent, child.prediction, factor.observation)
        materialized.append(
            GaussianComponent(
                weight=float(probabilities[index] / retained_mass),
                mean=mean,
                covariance=covariance,
                identity_history=child.parent.identity_history + (child.label,),
            )
        )
    components = tuple(materialized)
    flags = []
    if local_prior:
        flags.append("local_prior_approximation")
    if discarded_mass > 1e-15:
        flags.append("mixture_mass_discarded")
    if config.greedy:
        flags.append("greedy")
    if ineligible_positive_prior:
        flags.append("ineligible_positive_prior_mass")
    new_state = FilterState(
        components=components,
        consumed_observation_ids=state.consumed_observation_ids + factor.observation_ids,
    )
    return UpdateResult(
        state=new_state,
        predictive_log_density=predictive_log_density,
        association_probabilities=association,
        background_probability=background_probability,
        retained_pre_normalization_mass=retained_mass,
        discarded_pre_normalization_mass=discarded_mass,
        status="updated",
        flags=tuple(flags),
    )
