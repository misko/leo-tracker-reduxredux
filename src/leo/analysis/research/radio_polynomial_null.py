"""Training-frozen support-integrated radio-polynomial prediction null.

This pure analyzer is an equal-row, equal-noise descriptive comparator for the
catalogue model.  It fits line, quadratic, and cubic receiver-relative CFO
polynomials on an explicit chronological training prefix, freezes each fit,
and scores the identical future suffix once.  Coefficient uncertainty from the
training fit is propagated into the dense future predictive covariance.

The null does not rank NORADs, produce identity probabilities, calibrate a
threshold, or authorize execution on the opened long arcs.  It is intended to
be pinned by a later execution amendment after synthetic qualification.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
from numpy.typing import NDArray

from leo.contracts.catalogue_association import (
    PhysicalEpisodeGraphV1,
    SupportIntegratedCfoObservationV1,
)
from leo.contracts.digests import canonical_digest

_ALGORITHM_VERSION = "training-frozen-support-integrated-radio-polynomial-null-v1"


class RadioPolynomialNullInputError(ValueError):
    """The graph, partition, or frozen null configuration is invalid."""


class RadioPolynomialNullNumericalError(ValueError):
    """A weighted fit or predictive score was singular or unrepresentable."""


@dataclass(frozen=True, slots=True)
class RadioPolynomialNullConfig:
    training_observation_ids: tuple[str, ...]
    evaluation_observation_ids: tuple[str, ...]
    polynomial_degrees: tuple[int, int, int] = (1, 2, 3)
    calendar_block_duration_s: float = 1.0
    maximum_observation_count: int = 4_096
    maximum_dense_evaluation_rows: int = 2_048

    def __post_init__(self) -> None:
        if self.polynomial_degrees != (1, 2, 3):
            raise RadioPolynomialNullInputError("null degrees must be exactly line/quadratic/cubic")
        if len(self.training_observation_ids) < 4 or not self.evaluation_observation_ids:
            raise RadioPolynomialNullInputError(
                "null requires at least four training rows and one future row"
            )
        if (
            len(set(self.training_observation_ids)) != len(self.training_observation_ids)
            or len(set(self.evaluation_observation_ids)) != len(self.evaluation_observation_ids)
            or set(self.training_observation_ids) & set(self.evaluation_observation_ids)
        ):
            raise RadioPolynomialNullInputError(
                "training and future observation inventories must be unique and disjoint"
            )
        if (
            not math.isfinite(self.calendar_block_duration_s)
            or self.calendar_block_duration_s <= 0.0
            or self.maximum_observation_count < 5
            or self.maximum_dense_evaluation_rows < 1
        ):
            raise RadioPolynomialNullInputError("null work bounds and block duration are invalid")


@dataclass(frozen=True, slots=True)
class RadioPolynomialNullScore:
    degree: int
    reference_utc_ns: int
    coefficient_units: tuple[str, ...]
    coefficients: tuple[float, ...]
    coefficient_covariance: tuple[tuple[float, ...], ...]
    training_observation_count: int
    evaluation_observation_count: int
    evaluation_calendar_block_count: int
    training_rms_hz: float
    evaluation_pooled_rms_hz: float
    evaluation_equal_calendar_block_rms_hz: float
    evaluation_predictive_negative_log_likelihood: float
    evaluation_predictive_log_determinant_hz2: float
    evaluation_predictive_mahalanobis_squared: float
    fit_rank: int
    fit_condition_number: float


@dataclass(frozen=True, slots=True)
class RadioPolynomialNullResult:
    graph_content_digest: str
    observation_partition_digest: str
    training_observation_ids: tuple[str, ...]
    evaluation_observation_ids: tuple[str, ...]
    scores: tuple[RadioPolynomialNullScore, ...]
    algorithm_version: Literal["training-frozen-support-integrated-radio-polynomial-null-v1"] = (
        field(
            default="training-frozen-support-integrated-radio-polynomial-null-v1",
            init=False,
        )
    )
    same_observation_partition_for_all_degrees: Literal[True] = field(default=True, init=False)
    support_integrated_design: Literal[True] = field(default=True, init=False)
    observation_uncertainty_used: Literal[True] = field(default=True, init=False)
    training_only_fit: Literal[True] = field(default=True, init=False)
    future_scored_once_without_refit: Literal[True] = field(default=True, init=False)
    thresholds_are_unset: Literal[True] = field(default=True, init=False)
    identity_probability_produced: Literal[False] = field(default=False, init=False)
    association_gate_produced: Literal[False] = field(default=False, init=False)


def support_integrated_polynomial_design_row(
    observation: SupportIntegratedCfoObservationV1,
    *,
    reference_utc_ns: int,
    degree: int,
) -> tuple[float, ...]:
    """Return exact degree-0..3 aperture-averaged polynomial basis values."""

    if degree not in (1, 2, 3):
        raise RadioPolynomialNullInputError("support-integrated degree must be 1, 2, or 3")
    if reference_utc_ns <= 0:
        raise RadioPolynomialNullInputError("polynomial reference UTC must be positive")
    center_offset_s = (observation.support_center_utc_ns - reference_utc_ns) / 1e9
    raw_support_moments = tuple(
        math.factorial(index) * value
        for index, value in enumerate(observation.factorial_support_moments_s)
    )
    design: list[float] = []
    for power in range(degree + 1):
        integrated = sum(
            math.comb(power, support_power)
            * center_offset_s ** (power - support_power)
            * raw_support_moments[support_power]
            for support_power in range(power + 1)
        )
        if not math.isfinite(integrated):
            raise RadioPolynomialNullNumericalError("polynomial design is not finite")
        design.append(integrated)
    return tuple(design)


def score_radio_polynomial_null(
    graph: PhysicalEpisodeGraphV1,
    config: RadioPolynomialNullConfig,
) -> RadioPolynomialNullResult:
    """Fit every frozen null on training and score the same future rows once."""

    graph = _revalidate_graph(graph)
    config = _revalidate_config(config)
    if len(graph.observations) > config.maximum_observation_count:
        raise RadioPolynomialNullInputError("graph exceeds the declared null row-work cap")
    if len(config.evaluation_observation_ids) > config.maximum_dense_evaluation_rows:
        raise RadioPolynomialNullInputError("future rows exceed the declared dense-work cap")
    if len(graph.episodes) != 1:
        raise RadioPolynomialNullInputError("V1 radio-polynomial null requires exactly one episode")
    observation_by_id = {item.observation_id: item for item in graph.observations}
    all_ids = config.training_observation_ids + config.evaluation_observation_ids
    if set(all_ids) != set(observation_by_id) or len(all_ids) != len(observation_by_id):
        raise RadioPolynomialNullInputError(
            "training and future partitions must exhaust the exact graph"
        )
    training = tuple(observation_by_id[item] for item in config.training_observation_ids)
    evaluation = tuple(observation_by_id[item] for item in config.evaluation_observation_ids)
    if tuple(item.observation_id for item in training) != tuple(
        item.observation_id for item in sorted(training, key=lambda row: row.support_center_utc_ns)
    ) or tuple(item.observation_id for item in evaluation) != tuple(
        item.observation_id
        for item in sorted(evaluation, key=lambda row: row.support_center_utc_ns)
    ):
        raise RadioPolynomialNullInputError("partition inventories must be chronological")
    if training[-1].support_end_utc_ns > evaluation[0].support_start_utc_ns:
        raise RadioPolynomialNullInputError("training support must end before future support")

    reference_utc_ns = training[len(training) // 2].support_center_utc_ns
    scores = tuple(
        _fit_and_score(
            training,
            evaluation,
            reference_utc_ns=reference_utc_ns,
            degree=degree,
            calendar_block_duration_s=config.calendar_block_duration_s,
        )
        for degree in config.polynomial_degrees
    )
    partition_digest = canonical_digest(
        {
            "algorithm_version": _ALGORITHM_VERSION,
            "graph_content_digest": graph.content_digest,
            "training_observation_ids": config.training_observation_ids,
            "evaluation_observation_ids": config.evaluation_observation_ids,
            "polynomial_degrees": config.polynomial_degrees,
            "calendar_block_duration_s": config.calendar_block_duration_s,
        }
    )
    return RadioPolynomialNullResult(
        graph_content_digest=graph.content_digest,
        observation_partition_digest=partition_digest,
        training_observation_ids=config.training_observation_ids,
        evaluation_observation_ids=config.evaluation_observation_ids,
        scores=scores,
    )


def _fit_and_score(
    training: tuple[SupportIntegratedCfoObservationV1, ...],
    evaluation: tuple[SupportIntegratedCfoObservationV1, ...],
    *,
    reference_utc_ns: int,
    degree: int,
    calendar_block_duration_s: float,
) -> RadioPolynomialNullScore:
    design_training = _design_matrix(training, reference_utc_ns, degree)
    design_evaluation = _design_matrix(evaluation, reference_utc_ns, degree)
    response_training = np.asarray([item.measured_cfo_hz for item in training], dtype=np.float64)
    response_evaluation = np.asarray(
        [item.measured_cfo_hz for item in evaluation], dtype=np.float64
    )
    sigma_training = np.asarray(
        [item.standard_uncertainty_hz for item in training], dtype=np.float64
    )
    sigma_evaluation = np.asarray(
        [item.standard_uncertainty_hz for item in evaluation], dtype=np.float64
    )
    weighted_design = design_training / sigma_training[:, None]
    weighted_response = response_training / sigma_training
    coefficients, _, rank, singular_values = np.linalg.lstsq(
        weighted_design,
        weighted_response,
        rcond=None,
    )
    if rank != degree + 1 or singular_values.size != degree + 1:
        raise RadioPolynomialNullNumericalError("polynomial training design is rank deficient")
    condition_number = float(singular_values[0] / singular_values[-1])
    if not math.isfinite(condition_number):
        raise RadioPolynomialNullNumericalError("polynomial fit condition is not finite")
    information = weighted_design.T @ weighted_design
    try:
        information_cholesky = np.linalg.cholesky(information)
        identity = np.eye(degree + 1, dtype=np.float64)
        coefficient_covariance = np.linalg.solve(
            information_cholesky.T,
            np.linalg.solve(information_cholesky, identity),
        )
    except np.linalg.LinAlgError as error:
        raise RadioPolynomialNullNumericalError(
            "polynomial coefficient covariance is not positive definite"
        ) from error
    fitted_training = design_training @ coefficients
    fitted_evaluation = design_evaluation @ coefficients
    training_residual = response_training - fitted_training
    evaluation_residual = response_evaluation - fitted_evaluation
    predictive_covariance = np.diag(np.square(sigma_evaluation)) + (
        design_evaluation @ coefficient_covariance @ design_evaluation.T
    )
    predictive_nll, log_determinant, mahalanobis = _dense_gaussian_score(
        evaluation_residual,
        predictive_covariance,
    )
    block_mses: list[float] = []
    block_ns = round(calendar_block_duration_s * 1e9)
    if block_ns <= 0:
        raise RadioPolynomialNullInputError("calendar block duration underflows UTC ns")
    blocks: dict[int, list[float]] = {}
    for row, residual in zip(evaluation, evaluation_residual, strict=True):
        blocks.setdefault(row.support_center_utc_ns // block_ns, []).append(float(residual))
    for values in blocks.values():
        block_mses.append(sum(item * item for item in values) / len(values))
    return RadioPolynomialNullScore(
        degree=degree,
        reference_utc_ns=reference_utc_ns,
        coefficient_units=tuple(
            "Hz" if index == 0 else f"Hz/s^{index}" for index in range(degree + 1)
        ),
        coefficients=_finite_tuple(coefficients, "polynomial coefficients"),
        coefficient_covariance=tuple(
            _finite_tuple(row, "coefficient covariance") for row in coefficient_covariance
        ),
        training_observation_count=len(training),
        evaluation_observation_count=len(evaluation),
        evaluation_calendar_block_count=len(block_mses),
        training_rms_hz=_rms(training_residual),
        evaluation_pooled_rms_hz=_rms(evaluation_residual),
        evaluation_equal_calendar_block_rms_hz=math.sqrt(sum(block_mses) / len(block_mses)),
        evaluation_predictive_negative_log_likelihood=predictive_nll,
        evaluation_predictive_log_determinant_hz2=log_determinant,
        evaluation_predictive_mahalanobis_squared=mahalanobis,
        fit_rank=int(rank),
        fit_condition_number=condition_number,
    )


def _design_matrix(
    observations: tuple[SupportIntegratedCfoObservationV1, ...],
    reference_utc_ns: int,
    degree: int,
) -> NDArray[np.float64]:
    design = np.asarray(
        [
            support_integrated_polynomial_design_row(
                item,
                reference_utc_ns=reference_utc_ns,
                degree=degree,
            )
            for item in observations
        ],
        dtype=np.float64,
    )
    if not bool(np.all(np.isfinite(design))):
        raise RadioPolynomialNullNumericalError("polynomial design matrix is not finite")
    return design


def _dense_gaussian_score(
    residual: NDArray[np.float64],
    covariance: NDArray[np.float64],
) -> tuple[float, float, float]:
    try:
        cholesky = np.linalg.cholesky(covariance)
        whitened = np.linalg.solve(cholesky, residual)
    except np.linalg.LinAlgError as error:
        raise RadioPolynomialNullNumericalError(
            "future predictive covariance is not positive definite"
        ) from error
    diagonal = np.diag(cholesky)
    log_determinant = 2.0 * float(np.sum(np.log(diagonal)))
    mahalanobis = float(whitened @ whitened)
    negative_log_likelihood = 0.5 * (
        mahalanobis + log_determinant + residual.size * math.log(2.0 * math.pi)
    )
    if not all(
        math.isfinite(item) for item in (negative_log_likelihood, log_determinant, mahalanobis)
    ):
        raise RadioPolynomialNullNumericalError("future predictive score is not finite")
    return negative_log_likelihood, log_determinant, mahalanobis


def _rms(values: NDArray[np.float64]) -> float:
    result = math.sqrt(float(values @ values) / values.size)
    if not math.isfinite(result):
        raise RadioPolynomialNullNumericalError("polynomial residual RMS is not finite")
    return result


def _finite_tuple(values: NDArray[np.float64], label: str) -> tuple[float, ...]:
    result = tuple(float(item) for item in values)
    if any(not math.isfinite(item) for item in result):
        raise RadioPolynomialNullNumericalError(f"{label} are not finite")
    return result


def _revalidate_graph(graph: PhysicalEpisodeGraphV1) -> PhysicalEpisodeGraphV1:
    try:
        return PhysicalEpisodeGraphV1.model_validate(graph.model_dump(mode="json"))
    except (AttributeError, TypeError, ValueError) as error:
        raise RadioPolynomialNullInputError("physical episode graph is invalid") from error


def _revalidate_config(config: RadioPolynomialNullConfig) -> RadioPolynomialNullConfig:
    try:
        return RadioPolynomialNullConfig(
            training_observation_ids=tuple(config.training_observation_ids),
            evaluation_observation_ids=tuple(config.evaluation_observation_ids),
            polynomial_degrees=tuple(config.polynomial_degrees),  # type: ignore[arg-type]
            calendar_block_duration_s=config.calendar_block_duration_s,
            maximum_observation_count=config.maximum_observation_count,
            maximum_dense_evaluation_rows=config.maximum_dense_evaluation_rows,
        )
    except (AttributeError, TypeError, ValueError) as error:
        raise RadioPolynomialNullInputError("radio-polynomial configuration is invalid") from error


__all__ = [
    "RadioPolynomialNullConfig",
    "RadioPolynomialNullInputError",
    "RadioPolynomialNullNumericalError",
    "RadioPolynomialNullResult",
    "RadioPolynomialNullScore",
    "score_radio_polynomial_null",
    "support_integrated_polynomial_design_row",
]
