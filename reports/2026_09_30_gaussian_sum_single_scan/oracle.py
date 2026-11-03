"""Independent numerical oracles for the Gaussian-sum prototype.

This module deliberately does not import the production implementation.  The
linear oracle uses direct conditioning of a joint Gaussian; the grid oracle
uses normalized quadrature.  Both are intentionally small and unbounded by the
production mixture policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import log, pi
from typing import Callable, Iterable

import numpy as np


Array = np.ndarray


@dataclass(frozen=True)
class OracleComponent:
    weight: float
    mean: Array
    covariance: Array
    history: tuple[str, ...] = ()


@dataclass(frozen=True)
class LinearAlternative:
    label: str
    prior: float
    matrix: Array
    intercept: Array
    covariance: Array


@dataclass(frozen=True)
class OracleResult:
    components: tuple[OracleComponent, ...]
    log_evidence: float
    association: dict[str, float]
    mean: Array
    covariance: Array


def _logsumexp(values: Array) -> float:
    top = float(np.max(values))
    return top + log(float(np.exp(values - top).sum()))


def log_normal(value: Array, mean: Array, covariance: Array) -> float:
    value, mean, covariance = map(lambda x: np.asarray(x, dtype=float), (value, mean, covariance))
    chol = np.linalg.cholesky(covariance)
    delta = np.linalg.solve(chol, value - mean)
    return float(-0.5 * (value.size * log(2 * pi) + 2 * np.log(np.diag(chol)).sum() + delta @ delta))


def mixture_moments(components: Iterable[OracleComponent]) -> tuple[Array, Array]:
    components = tuple(components)
    weights = np.asarray([c.weight for c in components])
    weights = weights / weights.sum()
    mean = sum(w * c.mean for w, c in zip(weights, components, strict=True))
    covariance = sum(
        w * (c.covariance + np.outer(c.mean - mean, c.mean - mean))
        for w, c in zip(weights, components, strict=True)
    )
    return mean, covariance


def exact_linear_update(
    components: Iterable[OracleComponent], observation: Array,
    alternatives: Iterable[LinearAlternative], *,
    background_prior: float = 0.0, background_log_likelihood: float = -np.inf,
) -> OracleResult:
    """Enumerate children and condition via the joint Gaussian covariance."""
    children: list[OracleComponent] = []
    logs: list[float] = []
    labels: list[str] = []
    observation = np.asarray(observation, dtype=float)
    for component in components:
        for alternative in alternatives:
            if component.weight <= 0 or alternative.prior <= 0:
                continue
            h = np.asarray(alternative.matrix, dtype=float)
            predicted = h @ component.mean + alternative.intercept
            innovation_cov = h @ component.covariance @ h.T + alternative.covariance
            cross = component.covariance @ h.T
            gain = np.linalg.solve(innovation_cov, cross.T).T
            mean = component.mean + gain @ (observation - predicted)
            covariance = component.covariance - gain @ cross.T
            covariance = (covariance + covariance.T) / 2
            score = log(component.weight) + log(alternative.prior) + log_normal(observation, predicted, innovation_cov)
            children.append(OracleComponent(0.0, mean, covariance, component.history + (alternative.label,)))
            logs.append(score)
            labels.append(alternative.label)
        if background_prior > 0:
            children.append(OracleComponent(0.0, component.mean.copy(), component.covariance.copy(), component.history + ("background",)))
            logs.append(log(component.weight) + log(background_prior) + background_log_likelihood)
            labels.append("background")
    log_evidence = _logsumexp(np.asarray(logs))
    weights = np.exp(np.asarray(logs) - log_evidence)
    normalized = tuple(OracleComponent(float(w), c.mean, c.covariance, c.history) for w, c in zip(weights, children, strict=True))
    association = {label: float(sum(w for w, lab in zip(weights, labels, strict=True) if lab == label)) for label in set(labels)}
    mean, covariance = mixture_moments(normalized)
    return OracleResult(normalized, log_evidence, association, mean, covariance)


def regional_grid_oracle(
    axes: tuple[Array, ...], prior_log_density: Callable[[Array], float],
    alternatives: dict[str, tuple[float, Callable[[Array], float]]], *,
    background: tuple[float, float] | None = None,
) -> OracleResult:
    """Normalize posterior density on a regular regional grid."""
    shape = tuple(len(axis) for axis in axes)
    points = np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1).reshape(-1, len(axes))
    cell = float(np.prod([np.mean(np.diff(axis)) for axis in axes]))
    logs, labels, point_indices = [], [], []
    for i, point in enumerate(points):
        base = prior_log_density(point)
        for label, (mass, likelihood) in alternatives.items():
            if mass > 0:
                logs.append(base + log(mass) + likelihood(point) + log(cell))
                labels.append(label)
                point_indices.append(i)
        if background is not None and background[0] > 0:
            logs.append(base + log(background[0]) + background[1] + log(cell))
            labels.append("background")
            point_indices.append(i)
    log_evidence = _logsumexp(np.asarray(logs))
    weights = np.exp(np.asarray(logs) - log_evidence)
    mean = sum(w * points[i] for w, i in zip(weights, point_indices, strict=True))
    covariance = sum(w * np.outer(points[i] - mean, points[i] - mean) for w, i in zip(weights, point_indices, strict=True))
    association = {label: float(sum(w for w, lab in zip(weights, labels, strict=True) if lab == label)) for label in set(labels)}
    # Grid cells are represented as zero-covariance atoms; aggregate moments are exact quadrature moments.
    components = tuple(OracleComponent(float(w), points[i], np.zeros((len(shape), len(shape))), (lab,)) for w, i, lab in zip(weights, point_indices, labels, strict=True))
    return OracleResult(components, log_evidence, association, mean, covariance)
