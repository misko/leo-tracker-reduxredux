from __future__ import annotations

import math
from dataclasses import replace

import numpy as np
import pytest

from leo.analysis.research.block_predictive_evidence import (
    BlockPredictiveEvidenceConfig,
    BlockPredictiveEvidenceResult,
    BlockPredictiveInputError,
    BlockPredictiveNumericalError,
    BlockPredictiveObservation,
    BlockPredictiveWorkLimitError,
    CalendarBlockCovariance,
    FamilyPriorWeight,
    FrozenLinearGaussianState,
    FrozenStateObservationModel,
    StatePredictiveSummary,
    block_predictive_evidence_result_payload,
    hypothesis_inventory_digest,
    observation_inventory_digest,
    score_block_predictive_evidence,
)
from leo.contracts.digests import canonical_digest

_BASE_UTC_NS = 1_800_000_000_000_000_000
_BLOCK_DURATION_NS = 1_000_000_000
_OFFSETS_NS = (
    100_000_000,
    300_000_000,
    1_100_000_000,
    1_300_000_000,
    2_100_000_000,
    2_400_000_000,
    3_100_000_000,
    3_400_000_000,
)
_NOISE_HZ = (0.2, -0.3, 0.1, -0.2, 0.4, -0.1, 0.3, -0.5)


def _observations() -> tuple[BlockPredictiveObservation, ...]:
    rows: list[BlockPredictiveObservation] = []
    for index, (offset_ns, noise_hz) in enumerate(zip(_OFFSETS_NS, _NOISE_HZ, strict=True)):
        center_ns = _BASE_UTC_NS + offset_ns
        local_time_s = offset_ns / 1e9
        rows.append(
            BlockPredictiveObservation(
                observation_id=canonical_digest({"block-predictive-observation": index}),
                support_start_utc_ns=center_ns - 10_000_000,
                support_center_utc_ns=center_ns,
                support_end_utc_ns=center_ns + 10_000_000,
                status="usable",
                measured_cfo_hz=80.0 + 1.7 * local_time_s + noise_hz,
                standard_uncertainty_hz=1.2 + 0.1 * (index % 2),
            )
        )
    return tuple(rows)


def _model_rows(
    observations: tuple[BlockPredictiveObservation, ...],
    *,
    base: str,
    parameter_count: int,
    prediction_sigma_hz: float,
) -> tuple[FrozenStateObservationModel, ...]:
    rows: list[FrozenStateObservationModel] = []
    for observation in observations:
        local_time_s = (observation.support_center_utc_ns - _BASE_UTC_NS) / 1e9
        design_row: tuple[float, ...]
        if base == "catalogue":
            base_prediction_hz = 65.0 + 1.5 * local_time_s
            design_row = (1.0, local_time_s)
        elif base == "null":
            base_prediction_hz = 70.0
            design_row = (1.0,)
        elif base == "radio":
            base_prediction_hz = 0.0
            design_row = (1.0, local_time_s, local_time_s**2)
        elif base == "common":
            base_prediction_hz = 0.0
            design_row = (1.0, local_time_s)
        else:  # pragma: no cover - helper misuse
            raise AssertionError(base)
        assert len(design_row) == parameter_count
        rows.append(
            FrozenStateObservationModel(
                observation_id=observation.observation_id,
                base_prediction_hz=base_prediction_hz,
                design_row=design_row,
                prediction_standard_uncertainty_hz=prediction_sigma_hz,
            )
        )
    return tuple(rows)


def _states(
    observations: tuple[BlockPredictiveObservation, ...],
) -> tuple[FrozenLinearGaussianState, ...]:
    return (
        FrozenLinearGaussianState(
            state_id="null-constant",
            family="null",
            model_authority_digest=canonical_digest({"authority": "null"}),
            log_prior_weight_within_family=0.0,
            parameter_prior_mean=(5.0,),
            parameter_prior_covariance=((25.0,),),
            observation_models=_model_rows(
                observations,
                base="null",
                parameter_count=1,
                prediction_sigma_hz=0.1,
            ),
        ),
        FrozenLinearGaussianState(
            state_id="catalogue-candidate",
            family="catalogue-orbit",
            model_authority_digest=canonical_digest({"authority": "catalogue"}),
            log_prior_weight_within_family=0.0,
            parameter_prior_mean=(12.0, 0.1),
            parameter_prior_covariance=((25.0, 2.0), (2.0, 1.5)),
            observation_models=_model_rows(
                observations,
                base="catalogue",
                parameter_count=2,
                prediction_sigma_hz=0.3,
            ),
        ),
        FrozenLinearGaussianState(
            state_id="radio-quadratic",
            family="radio-polynomial",
            model_authority_digest=canonical_digest({"authority": "radio"}),
            log_prior_weight_within_family=0.0,
            parameter_prior_mean=(75.0, 1.0, 0.0),
            parameter_prior_covariance=((36.0, 0.0, 0.0), (0.0, 4.0, 0.0), (0.0, 0.0, 1.0)),
            observation_models=_model_rows(
                observations,
                base="radio",
                parameter_count=3,
                prediction_sigma_hz=0.2,
            ),
        ),
    )


def _identical_states(
    observations: tuple[BlockPredictiveObservation, ...],
    *,
    split_catalogue: bool,
) -> tuple[FrozenLinearGaussianState, ...]:
    models = _model_rows(
        observations,
        base="common",
        parameter_count=2,
        prediction_sigma_hz=0.25,
    )

    def state(
        state_id: str,
        family: str,
        log_prior_weight: float,
    ) -> FrozenLinearGaussianState:
        return FrozenLinearGaussianState(
            state_id=state_id,
            family=family,  # type: ignore[arg-type]
            model_authority_digest=canonical_digest({"authority": "identical-model"}),
            log_prior_weight_within_family=log_prior_weight,
            parameter_prior_mean=(80.0, 1.7),
            parameter_prior_covariance=((16.0, 0.5), (0.5, 2.0)),
            observation_models=models,
        )

    catalogue = (
        (
            state("catalogue-a", "catalogue-orbit", -math.log(2.0)),
            state("catalogue-b", "catalogue-orbit", -math.log(2.0)),
        )
        if split_catalogue
        else (state("catalogue-one", "catalogue-orbit", 0.0),)
    )
    return (
        state("null-one", "null", 0.0),
        *catalogue,
        state("radio-one", "radio-polynomial", 0.0),
    )


def _config(
    observations: tuple[BlockPredictiveObservation, ...],
    states: tuple[FrozenLinearGaussianState, ...],
    **overrides: object,
) -> BlockPredictiveEvidenceConfig:
    values: dict[str, object] = {
        "training_observation_ids": tuple(item.observation_id for item in observations[:4]),
        "evaluation_observation_ids": tuple(item.observation_id for item in observations[4:]),
        "expected_observation_inventory_digest": observation_inventory_digest(observations),
        "expected_hypothesis_inventory_digest": hypothesis_inventory_digest(states),
        "family_prior_weights": (
            FamilyPriorWeight("null", math.log(0.2)),
            FamilyPriorWeight("catalogue-orbit", math.log(0.5)),
            FamilyPriorWeight("radio-polynomial", math.log(0.3)),
        ),
        "covariance": CalendarBlockCovariance(
            measurement_variance_scale=1.3,
            independent_variance_floor_hz2=0.7,
            block_common_variance_hz2=2.2,
            calibration_authority_digest=canonical_digest({"covariance": "synthetic"}),
            calibrated=False,
        ),
        "calendar_block_duration_ns": _BLOCK_DURATION_NS,
        "minimum_usable_evaluation_observations": 1,
        "minimum_usable_evaluation_blocks": 1,
        "minimum_evaluation_observation_coverage": 0.0,
        "minimum_evaluation_block_coverage": 0.0,
        "opportunity_inventory_complete": True,
    }
    values.update(overrides)
    return BlockPredictiveEvidenceConfig(**values)  # type: ignore[arg-type]


def _state_summary(
    result: BlockPredictiveEvidenceResult,
    state_id: str,
) -> StatePredictiveSummary:
    return next(item for item in result.states if item.state_id == state_id)


def test_block_scores_telescope_to_direct_dense_conditional_gaussian() -> None:
    observations = _observations()
    states = _states(observations)
    config = _config(observations, states)
    result = score_block_predictive_evidence(observations, states, config=config)
    state = next(item for item in states if item.state_id == "catalogue-candidate")
    summary = _state_summary(result, state.state_id)
    evaluation = observations[4:]
    models = {item.observation_id: item for item in state.observation_models}
    design = np.asarray([models[item.observation_id].design_row for item in evaluation])
    parameter_mean = np.asarray(summary.training_parameter_posterior_mean)
    parameter_covariance = np.asarray(summary.training_parameter_posterior_covariance)
    predictive_mean = (
        np.asarray([models[item.observation_id].base_prediction_hz for item in evaluation])
        + design @ parameter_mean
    )
    response = np.asarray([item.measured_cfo_hz for item in evaluation], dtype=float)
    diagonal = np.asarray(
        [
            config.covariance.measurement_variance_scale * item.standard_uncertainty_hz**2  # type: ignore[operator]
            + config.covariance.independent_variance_floor_hz2
            + models[item.observation_id].prediction_standard_uncertainty_hz ** 2
            for item in evaluation
        ]
    )
    measurement_covariance = np.diag(diagonal)
    for left, left_row in enumerate(evaluation):
        for right, right_row in enumerate(evaluation):
            if (
                left_row.support_center_utc_ns // _BLOCK_DURATION_NS
                == right_row.support_center_utc_ns // _BLOCK_DURATION_NS
            ):
                measurement_covariance[left, right] += config.covariance.block_common_variance_hz2
    predictive_covariance = measurement_covariance + design @ parameter_covariance @ design.T
    residual = response - predictive_mean
    sign, log_determinant = np.linalg.slogdet(predictive_covariance)
    expected_mahalanobis = float(residual @ np.linalg.solve(predictive_covariance, residual))
    expected_nll = 0.5 * (
        expected_mahalanobis + float(log_determinant) + len(evaluation) * math.log(2.0 * math.pi)
    )
    state_block_nll = math.fsum(
        next(
            item for item in block.state_scores if item.state_id == state.state_id
        ).predictive_negative_log_likelihood
        for block in result.blocks
    )

    assert sign == 1.0
    assert summary.evaluation_predictive_negative_log_likelihood == pytest.approx(
        expected_nll,
        rel=2e-13,
    )
    assert state_block_nll == pytest.approx(expected_nll, rel=2e-13)


def test_later_future_response_cannot_change_an_earlier_block_score() -> None:
    observations = _observations()
    states = _states(observations)
    first = score_block_predictive_evidence(
        observations,
        states,
        config=_config(observations, states),
    )
    changed_observations = (
        *observations[:-1],
        replace(
            observations[-1],
            measured_cfo_hz=observations[-1].measured_cfo_hz + 200.0,  # type: ignore[operator]
        ),
    )
    second = score_block_predictive_evidence(
        changed_observations,
        states,
        config=_config(changed_observations, states),
    )

    assert first.blocks[0] == second.blocks[0]
    assert first.blocks[1] != second.blocks[1]
    assert tuple(
        (
            item.state_id,
            item.training_parameter_posterior_mean,
            item.training_parameter_posterior_covariance,
            item.normalized_model_mass_after_training,
        )
        for item in first.states
    ) == tuple(
        (
            item.state_id,
            item.training_parameter_posterior_mean,
            item.training_parameter_posterior_covariance,
            item.normalized_model_mass_after_training,
        )
        for item in second.states
    )


def test_state_order_and_equivalent_within_family_prior_split_are_invariant() -> None:
    observations = _observations()
    ordinary_states = _states(observations)
    ordered = score_block_predictive_evidence(
        observations,
        ordinary_states,
        config=_config(observations, ordinary_states),
    )
    reversed_states = tuple(reversed(ordinary_states))
    reordered = score_block_predictive_evidence(
        observations,
        reversed_states,
        config=_config(observations, reversed_states),
    )
    assert ordered == reordered

    one_catalogue = _identical_states(observations, split_catalogue=False)
    split_catalogue = _identical_states(observations, split_catalogue=True)
    one = score_block_predictive_evidence(
        observations,
        one_catalogue,
        config=_config(observations, one_catalogue),
    )
    split = score_block_predictive_evidence(
        observations,
        split_catalogue,
        config=_config(observations, split_catalogue),
    )
    assert split.evaluation_mixture_prequential_negative_log_likelihood == pytest.approx(
        one.evaluation_mixture_prequential_negative_log_likelihood,
        abs=2e-14,
    )
    for first_family, second_family in zip(one.families, split.families, strict=True):
        assert second_family.family == first_family.family
        assert second_family.normalized_model_mass_after_training == pytest.approx(
            first_family.normalized_model_mass_after_training,
            abs=2e-15,
        )
        assert second_family.normalized_model_mass_final == pytest.approx(
            first_family.normalized_model_mass_final,
            abs=2e-15,
        )
        assert second_family.evaluation_prequential_negative_log_likelihood == pytest.approx(
            first_family.evaluation_prequential_negative_log_likelihood,
            abs=2e-14,
        )
    family_masses = {
        item.family: item.normalized_model_mass_after_training for item in split.families
    }
    assert family_masses == pytest.approx(
        {"null": 0.2, "catalogue-orbit": 0.5, "radio-polynomial": 0.3},
        abs=2e-15,
    )


def test_missing_opportunities_are_retained_and_trigger_coverage_abstention() -> None:
    observations = _observations()
    observations = (
        *observations[:6],
        *(
            replace(
                item,
                status="missing",
                measured_cfo_hz=None,
                standard_uncertainty_hz=None,
                missing_reason="synthetic receiver dropout",
            )
            for item in observations[6:]
        ),
    )
    states = _states(observations)
    config = _config(
        observations,
        states,
        minimum_usable_evaluation_observations=3,
        minimum_usable_evaluation_blocks=2,
        minimum_evaluation_observation_coverage=0.75,
        minimum_evaluation_block_coverage=0.75,
    )
    result = score_block_predictive_evidence(observations, states, config=config)
    missing_block = result.blocks[-1]

    assert result.evaluation_observation_count == 4
    assert result.evaluation_usable_observation_count == 2
    assert result.evaluation_calendar_block_count == 2
    assert result.evaluation_usable_calendar_block_count == 1
    assert result.evaluation_observation_coverage == 0.5
    assert result.evaluation_block_coverage == 0.5
    assert result.covariance_parameters_calibrated is False
    assert result.opportunity_inventory_complete is True
    assert result.missing_opportunities_retained is True
    assert result.coverage_conditioned_on_observed_rows is False
    assert result.abstention_recommended is True
    assert set(result.abstention_diagnostics) == {
        "insufficient-evaluation-block-coverage",
        "insufficient-evaluation-observation-coverage",
        "insufficient-usable-evaluation-blocks",
        "insufficient-usable-evaluation-observations",
    }
    assert missing_block.opportunity_count == 2
    assert missing_block.usable_observation_count == 0
    assert missing_block.scored is False
    assert missing_block.mixture_predictive_negative_log_likelihood == pytest.approx(0.0)
    assert all(
        item.predictive_negative_log_likelihood == 0.0 for item in missing_block.state_scores
    )
    assert all(
        item.normalized_model_mass_before_block
        == pytest.approx(item.normalized_model_mass_after_block)
        for item in missing_block.family_scores
    )


def test_incomplete_opportunity_inventory_has_unknown_coverage_and_forces_abstention() -> None:
    observations = _observations()
    states = _states(observations)

    result = score_block_predictive_evidence(
        observations,
        states,
        config=_config(
            observations,
            states,
            opportunity_inventory_complete=False,
            minimum_evaluation_observation_coverage=1.0,
            minimum_evaluation_block_coverage=1.0,
        ),
    )

    assert result.evaluation_usable_observation_count == result.evaluation_observation_count
    assert result.evaluation_observation_coverage is None
    assert result.evaluation_block_coverage is None
    assert result.opportunity_inventory_complete is False
    assert result.missing_opportunities_retained is False
    assert result.coverage_conditioned_on_observed_rows is True
    assert result.abstention_recommended is True
    assert result.abstention_diagnostics == ("incomplete-opportunity-inventory",)
    assert tuple(
        observation_id for block in result.blocks for observation_id in block.observation_ids
    ) == tuple(item.observation_id for item in observations[4:])


def test_digest_closure_and_strict_inventory_and_work_caps() -> None:
    observations = _observations()
    states = _states(observations)
    config = _config(observations, states)
    result = score_block_predictive_evidence(observations, states, config=config)
    payload = block_predictive_evidence_result_payload(result)
    claimed = payload.pop("result_digest")
    assert claimed == canonical_digest(payload)

    tampered = replace(
        result,
        evaluation_mixture_prequential_negative_log_likelihood=(
            result.evaluation_mixture_prequential_negative_log_likelihood + 1.0
        ),
    )
    with pytest.raises(BlockPredictiveInputError, match="does not close"):
        block_predictive_evidence_result_payload(tampered)

    with pytest.raises(BlockPredictiveInputError, match="observation inventory digest"):
        score_block_predictive_evidence(
            observations,
            states,
            config=replace(
                config,
                expected_observation_inventory_digest=canonical_digest({"wrong": "observations"}),
            ),
        )
    with pytest.raises(BlockPredictiveInputError, match="hypothesis inventory digest"):
        score_block_predictive_evidence(
            observations,
            states,
            config=replace(
                config,
                expected_hypothesis_inventory_digest=canonical_digest({"wrong": "states"}),
            ),
        )
    with pytest.raises(BlockPredictiveWorkLimitError, match="state-row inventory"):
        score_block_predictive_evidence(
            observations,
            states,
            config=replace(config, maximum_state_observation_evaluations=23),
        )


def test_exact_common_inventory_and_calendar_partition_are_enforced() -> None:
    observations = _observations()
    states = _states(observations)
    first = states[0]
    mismatched_states = (
        replace(first, observation_models=tuple(reversed(first.observation_models))),
        *states[1:],
    )
    with pytest.raises(BlockPredictiveInputError, match="exact common chronological"):
        score_block_predictive_evidence(
            observations,
            mismatched_states,
            config=_config(observations, mismatched_states),
        )

    split_block_config = _config(
        observations,
        states,
        training_observation_ids=tuple(item.observation_id for item in observations[:3]),
        evaluation_observation_ids=tuple(item.observation_id for item in observations[3:]),
    )
    with pytest.raises(BlockPredictiveInputError, match="cannot be split"):
        score_block_predictive_evidence(observations, states, config=split_block_config)


def test_every_state_requires_a_proper_positive_definite_parameter_prior() -> None:
    observations = _observations()
    with pytest.raises(BlockPredictiveNumericalError, match="positive definite"):
        FrozenLinearGaussianState(
            state_id="singular-prior",
            family="null",
            model_authority_digest=canonical_digest({"authority": "singular"}),
            log_prior_weight_within_family=0.0,
            parameter_prior_mean=(0.0, 0.0),
            parameter_prior_covariance=((1.0, 1.0), (1.0, 1.0)),
            observation_models=_model_rows(
                observations,
                base="common",
                parameter_count=2,
                prediction_sigma_hz=0.0,
            ),
        )
