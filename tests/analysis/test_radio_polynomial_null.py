from __future__ import annotations

import math

import numpy as np
import pytest

from leo.analysis.research.radio_polynomial_null import (
    RadioPolynomialNullConfig,
    RadioPolynomialNullInputError,
    score_radio_polynomial_null,
    support_integrated_polynomial_design_row,
)
from leo.contracts.catalogue_association import (
    PhysicalCfoEpisodeV1,
    PhysicalEpisodeGraphV1,
    SupportIntegratedCfoObservationV1,
)
from leo.contracts.digests import canonical_digest

_BASE_UTC_NS = 1_800_000_000_000_000_000
_RAW_SECOND_MOMENT_S2 = 1.0 / 30_000.0


def _graph(*, evaluation_bias_hz: float = 0.0) -> PhysicalEpisodeGraphV1:
    episode_id = canonical_digest({"episode": "radio-null-synthetic"})
    observations: list[SupportIntegratedCfoObservationV1] = []
    for index in range(20):
        center_utc_ns = _BASE_UTC_NS + index * 1_000_000_000 + 10_000_000
        local_time_s = (center_utc_ns - _BASE_UTC_NS) / 1e9
        integrated_quadratic = (
            12_000.0 - 3_100.0 * local_time_s + 18.0 * (local_time_s**2 + _RAW_SECOND_MOMENT_S2)
        )
        measured = integrated_quadratic + (evaluation_bias_hz if index >= 12 else 0.0)
        observations.append(
            SupportIntegratedCfoObservationV1(
                observation_id=canonical_digest({"observation": index}),
                source_group_id=canonical_digest({"source-group": index}),
                episode_id=episode_id,
                receiver_path_id=canonical_digest({"path": "rx1-upper"}),
                hardware_epoch_id="radio-null-hardware-epoch",
                raw_recording_authority_digest=canonical_digest({"recording": "synthetic"}),
                recording_manifest_digest=canonical_digest({"manifest": "synthetic"}),
                stream_id="stream-1",
                source_binding_digest=canonical_digest({"source-binding": index}),
                source_sample_start=index * 2_500_000,
                source_sample_end=index * 2_500_000 + 50_000,
                support_start_utc_ns=center_utc_ns - 10_000_000,
                support_center_utc_ns=center_utc_ns,
                support_end_utc_ns=center_utc_ns + 10_000_000,
                measured_cfo_hz=measured,
                standard_uncertainty_hz=5.0,
                factorial_support_moments_s=(
                    1.0,
                    0.0,
                    _RAW_SECOND_MOMENT_S2 / 2.0,
                    0.0,
                ),
            )
        )
    episode = PhysicalCfoEpisodeV1(
        episode_id=episode_id,
        dwell_id=canonical_digest({"dwell": "synthetic"}),
        lane_id=canonical_digest({"lane": "synthetic"}),
        order_index=0,
        continuity_component_id=canonical_digest({"component": "synthetic"}),
        observation_ids=tuple(item.observation_id for item in observations),
    )
    return PhysicalEpisodeGraphV1.create(observations=tuple(observations), episodes=(episode,))


def _config(graph: PhysicalEpisodeGraphV1) -> RadioPolynomialNullConfig:
    identities = tuple(item.observation_id for item in graph.observations)
    return RadioPolynomialNullConfig(
        training_observation_ids=identities[:12],
        evaluation_observation_ids=identities[12:],
    )


def test_support_integrated_basis_includes_aperture_moments() -> None:
    graph = _graph()
    row = graph.observations[5]
    design = support_integrated_polynomial_design_row(
        row,
        reference_utc_ns=_BASE_UTC_NS,
        degree=3,
    )
    center_s = (row.support_center_utc_ns - _BASE_UTC_NS) / 1e9

    assert design == pytest.approx(
        (
            1.0,
            center_s,
            center_s**2 + _RAW_SECOND_MOMENT_S2,
            center_s**3 + 3.0 * center_s * _RAW_SECOND_MOMENT_S2,
        )
    )


def test_quadratic_and_cubic_predict_synthetic_curvature_but_line_does_not() -> None:
    graph = _graph()
    result = score_radio_polynomial_null(graph, _config(graph))
    scores = {item.degree: item for item in result.scores}

    assert tuple(scores) == (1, 2, 3)
    assert scores[1].evaluation_pooled_rms_hz > 100.0
    assert scores[2].training_rms_hz < 1e-8
    assert scores[2].evaluation_pooled_rms_hz < 1e-8
    assert scores[3].evaluation_pooled_rms_hz < 1e-8
    assert all(item.evaluation_observation_count == 8 for item in result.scores)
    assert all(item.evaluation_calendar_block_count == 8 for item in result.scores)
    assert result.thresholds_are_unset is True
    assert result.identity_probability_produced is False
    assert result.association_gate_produced is False


def test_future_response_does_not_change_training_fit() -> None:
    graph = _graph()
    changed = _graph(evaluation_bias_hz=250.0)
    first = score_radio_polynomial_null(graph, _config(graph))
    second = score_radio_polynomial_null(changed, _config(changed))

    assert tuple(item.coefficients for item in first.scores) == tuple(
        item.coefficients for item in second.scores
    )
    assert tuple(item.coefficient_covariance for item in first.scores) == tuple(
        item.coefficient_covariance for item in second.scores
    )
    assert first.observation_partition_digest != second.observation_partition_digest
    assert first.scores[2].evaluation_pooled_rms_hz < 1e-8
    assert second.scores[2].evaluation_pooled_rms_hz == pytest.approx(250.0)


def test_predictive_score_matches_direct_dense_gaussian() -> None:
    graph = _graph(evaluation_bias_hz=12.0)
    result = score_radio_polynomial_null(graph, _config(graph))
    score = result.scores[1]
    evaluation = graph.observations[12:]
    design = np.asarray(
        [
            support_integrated_polynomial_design_row(
                row,
                reference_utc_ns=score.reference_utc_ns,
                degree=score.degree,
            )
            for row in evaluation
        ]
    )
    coefficients = np.asarray(score.coefficients)
    coefficient_covariance = np.asarray(score.coefficient_covariance)
    residual = np.asarray([row.measured_cfo_hz for row in evaluation]) - design @ coefficients
    covariance = np.diag([row.standard_uncertainty_hz**2 for row in evaluation]) + (
        design @ coefficient_covariance @ design.T
    )
    sign, log_determinant = np.linalg.slogdet(covariance)
    expected_mahalanobis = float(residual @ np.linalg.solve(covariance, residual))
    expected_nll = 0.5 * (
        expected_mahalanobis + float(log_determinant) + len(evaluation) * math.log(2.0 * math.pi)
    )

    assert sign == 1.0
    assert score.evaluation_predictive_mahalanobis_squared == pytest.approx(
        expected_mahalanobis,
        rel=1e-12,
    )
    assert score.evaluation_predictive_negative_log_likelihood == pytest.approx(
        expected_nll,
        rel=1e-12,
    )


def test_partition_must_be_exhaustive_chronological_and_bounded() -> None:
    graph = _graph()
    identities = tuple(item.observation_id for item in graph.observations)
    missing = RadioPolynomialNullConfig(
        training_observation_ids=identities[:12],
        evaluation_observation_ids=identities[13:],
    )
    with pytest.raises(RadioPolynomialNullInputError, match="exhaust"):
        score_radio_polynomial_null(graph, missing)

    reversed_training = RadioPolynomialNullConfig(
        training_observation_ids=tuple(reversed(identities[:12])),
        evaluation_observation_ids=identities[12:],
    )
    with pytest.raises(RadioPolynomialNullInputError, match="chronological"):
        score_radio_polynomial_null(graph, reversed_training)

    bounded = RadioPolynomialNullConfig(
        training_observation_ids=identities[:12],
        evaluation_observation_ids=identities[12:],
        maximum_observation_count=19,
    )
    with pytest.raises(RadioPolynomialNullInputError, match="row-work cap"):
        score_radio_polynomial_null(graph, bounded)


def test_nested_graph_model_copy_poison_is_rejected_before_fit() -> None:
    graph = _graph()
    first = graph.observations[0].model_copy(update={"measured_cfo_hz": 1e300})
    poisoned = graph.model_copy(update={"observations": (first, *graph.observations[1:])})

    with pytest.raises(RadioPolynomialNullInputError, match="graph is invalid"):
        score_radio_polynomial_null(poisoned, _config(graph))
