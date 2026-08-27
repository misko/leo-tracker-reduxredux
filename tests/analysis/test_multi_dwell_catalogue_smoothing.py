from __future__ import annotations

import ast
import itertools
import math
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import numpy as np
import pytest

from leo.analysis import multi_dwell_catalogue_smoothing as smoothing_module
from leo.analysis.multi_dwell_catalogue_smoothing import (
    MultiDwellCatalogueFilterResult,
    MultiDwellFilterConfig,
    MultiDwellInputError,
    MultiDwellNumericalError,
    MultiDwellWorkLimitError,
    SyntheticCandidateDwellPrediction,
    SyntheticCandidateTrajectory,
    SyntheticCfoDwell,
    SyntheticMultiDwellPredictionBank,
    filter_multi_dwell_catalogue_modes,
    marginalize_dwell_nuisance,
)

_BASE_UTC_NS = 1_900_000_000_000_000_000
_SUPPORT_OFFSETS_S = (-1.5, -0.5, 0.5, 1.5)
_CATALOG_NUMBERS = (101, 202)


def _curve(catalog_number: int, dwell_index: int) -> tuple[float, ...]:
    if catalog_number == 101:
        quadratic = 4.0 + 0.2 * dwell_index
        cubic = 0.30
    elif catalog_number == 202:
        quadratic = -4.0 + 0.1 * dwell_index
        cubic = -0.25
    else:
        quadratic = 1.5 + 0.05 * catalog_number
        cubic = 0.10
    return tuple(quadratic * item**2 + cubic * item**3 for item in _SUPPORT_OFFSETS_S)


def _fixture(
    assignments: tuple[int | None, ...],
    *,
    hardware_epochs: tuple[str, ...] | None = None,
    drift_by_epoch: dict[str, float] | None = None,
    dwell_offsets_hz: tuple[float, ...] | None = None,
    candidate_numbers: tuple[int, ...] = _CATALOG_NUMBERS,
    curves: dict[tuple[int, int], tuple[float, ...]] | None = None,
    center_step_s: int = 10,
) -> tuple[tuple[SyntheticCfoDwell, ...], SyntheticMultiDwellPredictionBank]:
    count = len(assignments)
    hardware_epochs = hardware_epochs or tuple("epoch-a" for _ in assignments)
    drift_by_epoch = drift_by_epoch or {item: 0.65 for item in hardware_epochs}
    dwell_offsets_hz = dwell_offsets_hz or tuple(8.0 - 3.0 * index for index in range(count))
    if not (
        len(hardware_epochs) == count
        and len(dwell_offsets_hz) == count
        and set(hardware_epochs) <= set(drift_by_epoch)
    ):
        raise AssertionError("invalid synthetic fixture lengths")
    curve_lookup = {
        (catalog_number, dwell_index): (
            _curve(catalog_number, dwell_index)
            if curves is None
            else curves[catalog_number, dwell_index]
        )
        for catalog_number in candidate_numbers
        for dwell_index in range(count)
    }
    dwells: list[SyntheticCfoDwell] = []
    for dwell_index, identity in enumerate(assignments):
        prediction = (
            tuple(0.0 for _ in _SUPPORT_OFFSETS_S)
            if identity is None
            else curve_lookup[identity, dwell_index]
        )
        drift = drift_by_epoch[hardware_epochs[dwell_index]]
        measured = tuple(
            predicted + dwell_offsets_hz[dwell_index] + drift * support_offset
            for predicted, support_offset in zip(
                prediction,
                _SUPPORT_OFFSETS_S,
                strict=True,
            )
        )
        dwells.append(
            SyntheticCfoDwell(
                dwell_id=f"dwell-{dwell_index}",
                center_utc_ns=_BASE_UTC_NS + dwell_index * center_step_s * 1_000_000_000,
                hardware_epoch_id=hardware_epochs[dwell_index],
                support_offsets_s=_SUPPORT_OFFSETS_S,
                measured_cfo_hz=measured,
                measurement_standard_uncertainties_hz=tuple(0.10 for _ in _SUPPORT_OFFSETS_S),
            )
        )
    candidates = tuple(
        SyntheticCandidateTrajectory(
            catalog_number=catalog_number,
            dwell_predictions=tuple(
                SyntheticCandidateDwellPrediction(
                    dwell_id=f"dwell-{dwell_index}",
                    predicted_cfo_hz=curve_lookup[catalog_number, dwell_index],
                    prediction_standard_uncertainties_hz=tuple(0.10 for _ in _SUPPORT_OFFSETS_S),
                )
                for dwell_index in range(count)
            ),
        )
        for catalog_number in candidate_numbers
    )
    bank = SyntheticMultiDwellPredictionBank(
        dwell_ids=tuple(item.dwell_id for item in dwells),
        candidates=candidates,
        source_candidate_count=len(candidates),
    )
    return tuple(dwells), bank


def _config(**changes: object) -> MultiDwellFilterConfig:
    base: dict[str, object] = {
        "maximum_distinct_catalogues": 2,
        "retained_mode_limit": 128,
        "maximum_evaluated_extensions": 100_000,
        "initial_drift_standard_uncertainty_hz_per_s": 3.0,
        "drift_random_walk_standard_uncertainty_hz_per_s_per_sqrt_s": 0.001,
        "dwell_offset_prior_standard_uncertainty_hz": 50.0,
        "maximum_nuisance_propagation_gap_s": 60.0,
        "null_prediction_standard_uncertainty_hz": 0.10,
        "initial_null_log_weight": 0.0,
        "initial_candidate_log_weight": 0.0,
        "null_stay_log_weight": 0.0,
        "null_to_candidate_log_weight": -1.0,
        "candidate_to_null_log_weight": -1.0,
        "same_identity_log_weight": 0.0,
        "handoff_log_weight": -2.0,
    }
    base.update(changes)
    return MultiDwellFilterConfig(**base)  # type: ignore[arg-type]


def test_null_sequence_remains_an_explicit_k_zero_mode() -> None:
    dwells, bank = _fixture((None, None, None, None))

    result = filter_multi_dwell_catalogue_modes(dwells, bank, config=_config())

    nearest = result.final_modes[0]
    assert nearest.assignments == (None, None, None, None)
    assert nearest.active_catalog_numbers == ()
    assert result.rolling[-1].nearest_identity is None
    assert result.final_abstention_recommended
    assert "null-nearest" in result.final_abstention_diagnostics
    assert not result.identity_claimed


def test_shared_identity_collapses_nuisance_but_not_discrete_inventory() -> None:
    dwells, bank = _fixture((101, 101, 101, 101))

    result = filter_multi_dwell_catalogue_modes(dwells, bank, config=_config())

    nearest = result.final_modes[0]
    assert nearest.assignments == (101, 101, 101, 101)
    assert nearest.active_catalog_numbers == (101,)
    assert any(item.assignments != nearest.assignments for item in result.final_modes)
    assert not result.discrete_modes_moment_matched
    assert result.fixed_lag_backward_smoothing_performed is False
    assert result.ecm_performed is False


def test_handoff_is_retained_as_a_k_two_path() -> None:
    dwells, bank = _fixture((101, 101, 202, 202))

    result = filter_multi_dwell_catalogue_modes(dwells, bank, config=_config())

    nearest = result.final_modes[0]
    assert nearest.assignments == (101, 101, 202, 202)
    assert nearest.active_catalog_numbers == (101, 202)
    assert len(nearest.active_catalog_numbers) == 2


def test_maximum_distinct_catalogues_prevents_silent_k_three_growth() -> None:
    candidate_numbers = (101, 202, 303)
    dwells, bank = _fixture((101, 202, 303), candidate_numbers=candidate_numbers)

    result = filter_multi_dwell_catalogue_modes(
        dwells,
        bank,
        config=_config(maximum_distinct_catalogues=2, retained_mode_limit=256),
    )

    assert all(len(item.active_catalog_numbers) <= 2 for item in result.final_modes)
    assert all(item.assignments != (101, 202, 303) for item in result.final_modes)
    assert not result.simultaneous_two_emitter_modelled
    assert result.emitter_model == "one-source-state-per-dwell-k02-distinct-history-v1"

    with pytest.raises(MultiDwellInputError, match="at most two distinct"):
        _config(maximum_distinct_catalogues=3)


def test_drift_and_dwell_local_offset_are_recovered_under_proper_gauge() -> None:
    offsets = (12.0, -7.0, 4.5, 19.0)
    dwells, bank = _fixture(
        (101, 101, 101, 101),
        drift_by_epoch={"epoch-a": 0.80},
        dwell_offsets_hz=offsets,
    )

    result = filter_multi_dwell_catalogue_modes(dwells, bank, config=_config())

    for index, rolling in enumerate(result.rolling):
        nuisance = rolling.modes[0].nuisance
        assert nuisance.filtered_drift_mean_hz_per_s == pytest.approx(0.80, abs=0.02)
        assert nuisance.dwell_offset_mean_hz == pytest.approx(offsets[index], abs=0.02)
        assert nuisance.filtered_drift_standard_uncertainty_hz_per_s > 0.0
        assert nuisance.dwell_offset_standard_uncertainty_hz > 0.0
    assert result.rolling[1].modes[0].nuisance.predicted_drift_mean_hz_per_s == pytest.approx(
        result.rolling[0].modes[0].nuisance.filtered_drift_mean_hz_per_s
    )


def test_hardware_epoch_change_resets_shared_drift_prior() -> None:
    epochs = ("epoch-a", "epoch-a", "epoch-b", "epoch-b")
    dwells, bank = _fixture(
        (101, 101, 101, 101),
        hardware_epochs=epochs,
        drift_by_epoch={"epoch-a": 0.9, "epoch-b": -1.1},
    )

    result = filter_multi_dwell_catalogue_modes(dwells, bank, config=_config())

    reset = result.rolling[2].modes[0].nuisance
    assert reset.reset_reason == "hardware-epoch-change"
    assert reset.predicted_drift_mean_hz_per_s == 0.0
    assert reset.predicted_drift_standard_uncertainty_hz_per_s == 3.0
    assert reset.filtered_drift_mean_hz_per_s == pytest.approx(-1.1, abs=0.02)
    assert result.rolling[3].modes[0].nuisance.reset_reason is None


def test_validity_gap_resets_even_inside_one_hardware_epoch() -> None:
    dwells, bank = _fixture((101, 101), center_step_s=120)

    result = filter_multi_dwell_catalogue_modes(
        dwells,
        bank,
        config=_config(maximum_nuisance_propagation_gap_s=60.0),
    )

    assert result.rolling[1].modes[0].nuisance.reset_reason == "validity-gap"
    assert result.rolling[1].modes[0].nuisance.predicted_drift_mean_hz_per_s == 0.0


def test_future_response_poison_cannot_change_earlier_rolling_receipts() -> None:
    dwells, bank = _fixture((101, 101, 101, 101))
    poisoned_last = replace(
        dwells[-1],
        measured_cfo_hz=tuple(
            value + poison
            for value, poison in zip(
                dwells[-1].measured_cfo_hz,
                (100.0, -100.0, 100.0, -100.0),
                strict=True,
            )
        ),
    )

    original = filter_multi_dwell_catalogue_modes(dwells, bank, config=_config())
    poisoned = filter_multi_dwell_catalogue_modes(
        (*dwells[:-1], poisoned_last),
        bank,
        config=_config(),
    )

    assert original.rolling[:-1] == poisoned.rolling[:-1]
    assert repr(original.rolling[:-1]).encode() == repr(poisoned.rolling[:-1]).encode()
    assert original.rolling[-1] != poisoned.rolling[-1]
    assert all(item.score_before_assimilation for item in original.rolling)
    assert all(
        not item.later_response_used_for_current_score_or_assimilation for item in original.rolling
    )
    assert all(item.whole_input_envelope_validated_before_filtering for item in original.rolling)

    invalid_last = replace(dwells[-1])
    object.__setattr__(
        invalid_last,
        "measured_cfo_hz",
        (*invalid_last.measured_cfo_hz[:-1], math.nan),
    )
    with pytest.raises(MultiDwellInputError, match="finite"):
        filter_multi_dwell_catalogue_modes(
            (*dwells[:-1], invalid_last),
            bank,
            config=_config(),
        )


def test_close_catalogue_modes_produce_explicit_descriptive_ambiguity() -> None:
    assignments = (101, 101, 101)
    curves = {
        (catalog_number, dwell_index): _curve(101, dwell_index)
        for catalog_number in _CATALOG_NUMBERS
        for dwell_index in range(len(assignments))
    }
    curves.update(
        {
            (202, dwell_index): tuple(
                value + 0.01 * (support_offset**2 - 1.25)
                for value, support_offset in zip(
                    _curve(101, dwell_index),
                    _SUPPORT_OFFSETS_S,
                    strict=True,
                )
            )
            for dwell_index in range(len(assignments))
        }
    )
    dwells, bank = _fixture(assignments, curves=curves)

    result = filter_multi_dwell_catalogue_modes(
        dwells,
        bank,
        config=_config(descriptive_ambiguity_negative_log_joint_margin=1.0),
    )

    final = result.rolling[-1]
    assert final.identity_ambiguity_set == (101, 202)
    assert final.descriptive_close_mode_ambiguity
    assert final.abstention_recommended
    assert "descriptive-close-mode-ambiguity" in final.abstention_diagnostics
    assert not result.thresholds_are_calibrated


def test_early_close_modes_remain_separate_then_future_geometry_resolves_them() -> None:
    assignments = (101, 101, 101)
    curves = {
        (catalog_number, dwell_index): (
            _curve(101, dwell_index)
            if dwell_index < 2 or catalog_number == 101
            else _curve(202, dwell_index)
        )
        for catalog_number in _CATALOG_NUMBERS
        for dwell_index in range(len(assignments))
    }
    dwells, bank = _fixture(assignments, curves=curves)

    result = filter_multi_dwell_catalogue_modes(dwells, bank, config=_config())

    assert result.rolling[0].identity_ambiguity_set == (101, 202)
    assert result.rolling[1].exact_discrete_tie
    assert any(item.assignments == (101, 101) for item in result.rolling[1].modes)
    assert any(item.assignments == (202, 202) for item in result.rolling[1].modes)
    assert result.rolling[2].nearest_identity == 101
    assert not result.rolling[2].exact_discrete_tie


def test_null_and_identical_candidate_receive_equal_nuisance_opportunity() -> None:
    zero_curves = {
        (101, dwell_index): tuple(0.0 for _ in _SUPPORT_OFFSETS_S) for dwell_index in range(2)
    }
    dwells, bank = _fixture(
        (None, None),
        candidate_numbers=(101,),
        curves=zero_curves,
    )

    result = filter_multi_dwell_catalogue_modes(dwells, bank, config=_config())

    null_mode = next(item for item in result.rolling[0].modes if item.current_identity is None)
    candidate_mode = next(item for item in result.rolling[0].modes if item.current_identity == 101)
    assert null_mode.next_dwell_predictive_negative_log_likelihood == pytest.approx(
        candidate_mode.next_dwell_predictive_negative_log_likelihood,
        rel=0.0,
        abs=0.0,
    )
    assert null_mode.nuisance == candidate_mode.nuisance


def test_exact_tie_uses_canonical_identity_order_and_abstains() -> None:
    assignments = (101, 101)
    curves = {
        (catalog_number, dwell_index): _curve(101, dwell_index)
        for catalog_number in _CATALOG_NUMBERS
        for dwell_index in range(len(assignments))
    }
    dwells, bank = _fixture(assignments, curves=curves)

    first = filter_multi_dwell_catalogue_modes(dwells, bank, config=_config())
    second = filter_multi_dwell_catalogue_modes(dwells, bank, config=_config())

    assert first == second
    assert first.final_modes[0].assignments == (101, 101)
    assert first.rolling[-1].exact_discrete_tie
    assert first.rolling[-1].identity_ambiguity_set == (101, 202)
    assert "exact-discrete-tie" in first.final_abstention_diagnostics


def test_transition_potentials_are_normalized_for_every_parent() -> None:
    dwells, bank = _fixture((101, 101))

    result = filter_multi_dwell_catalogue_modes(dwells, bank, config=_config())

    assert result.evaluated_support_row_count == math.fsum(
        item.evaluated_support_row_count for item in result.rolling
    )
    assert math.fsum(
        math.exp(-item.transition_negative_log_probability) for item in result.rolling[0].modes
    ) == pytest.approx(1.0)
    by_parent: dict[tuple[int | None, ...], list[float]] = {}
    for item in result.rolling[1].modes:
        by_parent.setdefault(item.assignments[:-1], []).append(
            item.transition_negative_log_probability
        )
    assert set(by_parent) == {(None,), (101,), (202,)}
    for penalties in by_parent.values():
        assert math.fsum(math.exp(-item) for item in penalties) == pytest.approx(1.0)


def test_candidate_birth_and_handoff_family_mass_do_not_grow_with_catalogue_size() -> None:
    two_dwells, two_bank = _fixture((101, 101), candidate_numbers=(101, 202))
    three_dwells, three_bank = _fixture((101, 101), candidate_numbers=(101, 202, 303))

    two = filter_multi_dwell_catalogue_modes(two_dwells, two_bank, config=_config())
    three = filter_multi_dwell_catalogue_modes(
        three_dwells,
        three_bank,
        config=_config(retained_mode_limit=512),
    )

    def initial_candidate_mass(result: MultiDwellCatalogueFilterResult) -> float:
        rolling = result.rolling
        return math.fsum(
            math.exp(-item.transition_negative_log_probability)
            for item in rolling[0].modes
            if item.current_identity is not None
        )

    def transition_family_mass(
        result: MultiDwellCatalogueFilterResult,
        *,
        parent: int | None,
        family: str,
    ) -> float:
        rolling = result.rolling
        children = [item for item in rolling[1].modes if item.assignments[:-1] == (parent,)]
        if family == "birth":
            selected = [item for item in children if item.current_identity is not None]
        elif family == "handoff":
            selected = [
                item
                for item in children
                if item.current_identity is not None and item.current_identity != parent
            ]
        else:
            raise AssertionError("unknown family")
        return math.fsum(math.exp(-item.transition_negative_log_probability) for item in selected)

    assert initial_candidate_mass(two) == pytest.approx(initial_candidate_mass(three))
    assert transition_family_mass(two, parent=None, family="birth") == pytest.approx(
        transition_family_mass(three, parent=None, family="birth")
    )
    assert transition_family_mass(two, parent=101, family="handoff") == pytest.approx(
        transition_family_mass(three, parent=101, family="handoff")
    )


def test_beam_pruning_is_reported_and_recommends_abstention() -> None:
    dwells, bank = _fixture((101, 101, 101))

    result = filter_multi_dwell_catalogue_modes(
        dwells,
        bank,
        config=_config(retained_mode_limit=1),
    )

    assert result.any_pruning
    assert result.rolling[0].current_step_beam_pruned
    assert all(item.prior_or_current_beam_pruned for item in result.rolling)
    assert not result.rolling[0].mixture_predictive_conditioned_on_pruned_parent_beam
    assert all(
        item.mixture_predictive_conditioned_on_pruned_parent_beam for item in result.rolling[1:]
    )
    assert all("beam-pruned" in item.abstention_diagnostics for item in result.rolling)
    assert 0.0 < result.rolling[0].conditional_mass_retained_from_evaluated_extensions <= 1.0
    assert "beam-pruned" in result.final_abstention_diagnostics


def test_tied_cutoff_expands_inventory_instead_of_silently_splitting_tie() -> None:
    assignments = (101,)
    curves = {(catalog_number, 0): _curve(101, 0) for catalog_number in _CATALOG_NUMBERS}
    dwells, bank = _fixture(assignments, curves=curves)

    result = filter_multi_dwell_catalogue_modes(
        dwells,
        bank,
        config=_config(retained_mode_limit=1),
    )

    step = result.rolling[0]
    assert step.tie_expanded_retained_inventory
    assert step.retained_mode_count == 2
    assert step.exact_discrete_tie


def test_marginal_score_matches_direct_covariance_and_information_forms() -> None:
    residual = (5.0, -1.0, 3.0, 2.0)
    support = (-1.5, -0.5, 0.5, 1.5)
    sigmas = (0.5, 1.0, 1.5, 0.75)
    drift_mean = 0.4
    drift_sigma = 2.0
    offset_sigma = 3.0

    score = marginalize_dwell_nuisance(
        residual,
        support,
        sigmas,
        drift_prior_mean_hz_per_s=drift_mean,
        drift_prior_standard_uncertainty_hz_per_s=drift_sigma,
        dwell_offset_prior_standard_uncertainty_hz=offset_sigma,
    )

    design = np.column_stack((np.asarray(support), np.ones(len(support))))
    prior_mean = np.asarray((drift_mean, 0.0))
    prior_covariance = np.diag((drift_sigma**2, offset_sigma**2))
    noise_covariance = np.diag(np.square(sigmas))
    covariance = noise_covariance + design @ prior_covariance @ design.T
    centered = np.asarray(residual) - design @ prior_mean
    sign, log_determinant = np.linalg.slogdet(covariance)
    mahalanobis = float(centered @ np.linalg.solve(covariance, centered))
    expected_nll = 0.5 * (mahalanobis + log_determinant + len(residual) * math.log(2.0 * math.pi))
    posterior_covariance = np.linalg.inv(
        np.linalg.inv(prior_covariance) + design.T @ np.linalg.inv(noise_covariance) @ design
    )
    posterior_mean = posterior_covariance @ (
        np.linalg.inv(prior_covariance) @ prior_mean
        + design.T @ np.linalg.inv(noise_covariance) @ np.asarray(residual)
    )

    assert sign == 1.0
    assert score.mahalanobis_squared == pytest.approx(mahalanobis, rel=1e-12)
    assert score.log_determinant_covariance == pytest.approx(log_determinant, rel=1e-12)
    assert score.predictive_negative_log_likelihood == pytest.approx(expected_nll, rel=1e-12)
    assert score.drift_posterior_mean_hz_per_s == pytest.approx(posterior_mean[0], rel=1e-12)
    assert score.dwell_offset_posterior_mean_hz == pytest.approx(posterior_mean[1], rel=1e-12)
    assert score.drift_offset_posterior_covariance_hz2_per_s == pytest.approx(
        posterior_covariance[0, 1], rel=1e-12
    )


def test_fixed_path_sequential_innovation_nll_matches_direct_batch_evidence() -> None:
    dwells, bank = _fixture((101, 101, 101))
    config = _config()

    result = filter_multi_dwell_catalogue_modes(dwells, bank, config=config)

    sequential_nll = 0.0
    for dwell_index, rolling in enumerate(result.rolling, start=1):
        fixed_path = next(
            item for item in rolling.modes if item.assignments == (101,) * dwell_index
        )
        sequential_nll += fixed_path.next_dwell_predictive_negative_log_likelihood

    row_count = len(_SUPPORT_OFFSETS_S)
    total_rows = row_count * len(dwells)
    residual = np.empty(total_rows)
    covariance = np.zeros((total_rows, total_rows))
    independent_variance = 0.1**2 + 0.1**2
    drift_initial_variance = config.initial_drift_standard_uncertainty_hz_per_s**2
    drift_rw_variance_rate = config.drift_random_walk_standard_uncertainty_hz_per_s_per_sqrt_s**2
    offset_variance = config.dwell_offset_prior_standard_uncertainty_hz**2
    candidate = bank.candidates[0]
    for left_index, (left_dwell, left_prediction) in enumerate(
        zip(dwells, candidate.dwell_predictions, strict=True)
    ):
        left_slice = slice(left_index * row_count, (left_index + 1) * row_count)
        residual[left_slice] = np.asarray(left_dwell.measured_cfo_hz) - np.asarray(
            left_prediction.predicted_cfo_hz
        )
        covariance[left_slice, left_slice] += (
            np.eye(row_count) * independent_variance
            + np.ones((row_count, row_count)) * offset_variance
        )
        for right_index, right_dwell in enumerate(dwells):
            right_slice = slice(right_index * row_count, (right_index + 1) * row_count)
            elapsed_to_earlier_s = (
                min(left_dwell.center_utc_ns, right_dwell.center_utc_ns) - dwells[0].center_utc_ns
            ) / 1e9
            drift_covariance = (
                drift_initial_variance + drift_rw_variance_rate * elapsed_to_earlier_s
            )
            covariance[left_slice, right_slice] += drift_covariance * np.outer(
                _SUPPORT_OFFSETS_S,
                _SUPPORT_OFFSETS_S,
            )
    mean = np.tile(
        np.asarray(_SUPPORT_OFFSETS_S) * config.initial_drift_mean_hz_per_s,
        len(dwells),
    )
    centered = residual - mean
    sign, log_determinant = np.linalg.slogdet(covariance)
    expected_nll = 0.5 * (
        float(centered @ np.linalg.solve(covariance, centered))
        + log_determinant
        + total_rows * math.log(2.0 * math.pi)
    )

    assert sign == 1.0
    assert sequential_nll == pytest.approx(expected_nll, rel=2e-10, abs=2e-10)


def test_mixture_predictive_scores_telescope_to_direct_discrete_batch_evidence() -> None:
    dwells, bank = _fixture((101, 101))
    config = _config()

    result = filter_multi_dwell_catalogue_modes(dwells, bank, config=config)

    rolling_mixture_nll = math.fsum(
        item.mixture_predictive_negative_log_likelihood for item in result.rolling
    )
    minimum_path_score = min(item.cumulative_negative_log_joint for item in result.final_modes)
    output_path_evidence_nll = minimum_path_score - math.log(
        math.fsum(
            math.exp(-(item.cumulative_negative_log_joint - minimum_path_score))
            for item in result.final_modes
        )
    )

    identities = (None, 101, 202)
    initial_probability = {None: 0.5, 101: 0.25, 202: 0.25}
    null_birth_normalizer = math.exp(config.null_stay_log_weight) + math.exp(
        config.null_to_candidate_log_weight
    )
    candidate_transition_normalizer = (
        math.exp(config.candidate_to_null_log_weight)
        + math.exp(config.same_identity_log_weight)
        + math.exp(config.handoff_log_weight)
    )

    def transition_probability(previous: int | None, current: int | None) -> float:
        if previous is None:
            if current is None:
                return math.exp(config.null_stay_log_weight) / null_birth_normalizer
            return math.exp(config.null_to_candidate_log_weight) / null_birth_normalizer / 2.0
        if current is None:
            return math.exp(config.candidate_to_null_log_weight) / (candidate_transition_normalizer)
        if current == previous:
            return math.exp(config.same_identity_log_weight) / candidate_transition_normalizer
        return math.exp(config.handoff_log_weight) / candidate_transition_normalizer

    prediction_lookup = {
        (candidate.catalog_number, prediction.dwell_id): prediction.predicted_cfo_hz
        for candidate in bank.candidates
        for prediction in candidate.dwell_predictions
    }
    row_count = len(_SUPPORT_OFFSETS_S)
    total_rows = row_count * len(dwells)
    covariance = np.zeros((total_rows, total_rows))
    independent_variance = 0.1**2 + 0.1**2
    drift_initial_variance = config.initial_drift_standard_uncertainty_hz_per_s**2
    drift_rw_variance_rate = config.drift_random_walk_standard_uncertainty_hz_per_s_per_sqrt_s**2
    offset_variance = config.dwell_offset_prior_standard_uncertainty_hz**2
    for left_index, left_dwell in enumerate(dwells):
        left_slice = slice(left_index * row_count, (left_index + 1) * row_count)
        covariance[left_slice, left_slice] += (
            np.eye(row_count) * independent_variance
            + np.ones((row_count, row_count)) * offset_variance
        )
        for right_index, right_dwell in enumerate(dwells):
            right_slice = slice(right_index * row_count, (right_index + 1) * row_count)
            elapsed_to_earlier_s = (
                min(left_dwell.center_utc_ns, right_dwell.center_utc_ns) - dwells[0].center_utc_ns
            ) / 1e9
            drift_covariance = (
                drift_initial_variance + drift_rw_variance_rate * elapsed_to_earlier_s
            )
            covariance[left_slice, right_slice] += drift_covariance * np.outer(
                _SUPPORT_OFFSETS_S,
                _SUPPORT_OFFSETS_S,
            )
    mean = np.tile(
        np.asarray(_SUPPORT_OFFSETS_S) * config.initial_drift_mean_hz_per_s,
        len(dwells),
    )
    _, log_determinant = np.linalg.slogdet(covariance)
    direct_joint_scores: list[float] = []
    for path in itertools.product(identities, repeat=len(dwells)):
        residual_blocks: list[float] = []
        for dwell, identity in zip(dwells, path, strict=True):
            prediction = (
                tuple(0.0 for _ in _SUPPORT_OFFSETS_S)
                if identity is None
                else prediction_lookup[identity, dwell.dwell_id]
            )
            residual_blocks.extend(
                measured - predicted
                for measured, predicted in zip(
                    dwell.measured_cfo_hz,
                    prediction,
                    strict=True,
                )
            )
        centered = np.asarray(residual_blocks) - mean
        batch_nll = float(
            0.5
            * (
                float(centered @ np.linalg.solve(covariance, centered))
                + log_determinant
                + total_rows * math.log(2.0 * math.pi)
            )
        )
        path_probability = initial_probability[path[0]] * transition_probability(path[0], path[1])
        direct_joint_scores.append(batch_nll - math.log(path_probability))
    minimum_direct_score = min(direct_joint_scores)
    direct_mixture_nll = minimum_direct_score - math.log(
        math.fsum(math.exp(-(item - minimum_direct_score)) for item in direct_joint_scores)
    )

    assert not result.any_pruning
    assert all(
        not item.mixture_predictive_conditioned_on_pruned_parent_beam for item in result.rolling
    )
    assert rolling_mixture_nll == pytest.approx(output_path_evidence_nll, abs=2e-10)
    assert rolling_mixture_nll == pytest.approx(direct_mixture_nll, abs=2e-10)


def test_wrong_dwell_order_and_epoch_reentry_fail_closed() -> None:
    dwells, bank = _fixture((101, 101, 101))
    with pytest.raises(MultiDwellInputError, match="exact ordered dwell"):
        filter_multi_dwell_catalogue_modes(tuple(reversed(dwells)), bank, config=_config())

    reentered = (
        dwells[0],
        replace(dwells[1], hardware_epoch_id="epoch-b"),
        dwells[2],
    )
    with pytest.raises(MultiDwellInputError, match="cannot reappear"):
        filter_multi_dwell_catalogue_modes(reentered, bank, config=_config())

    overlapping_dwells, overlapping_bank = _fixture((101, 101), center_step_s=2)
    with pytest.raises(MultiDwellInputError, match="support intervals"):
        filter_multi_dwell_catalogue_modes(
            overlapping_dwells,
            overlapping_bank,
            config=_config(),
        )


def test_prediction_bank_requires_canonical_complete_coverage() -> None:
    dwells, bank = _fixture((101, 101))
    with pytest.raises(MultiDwellInputError, match="ordered by catalog_number"):
        SyntheticMultiDwellPredictionBank(
            dwell_ids=bank.dwell_ids,
            candidates=tuple(reversed(bank.candidates)),
            source_candidate_count=2,
        )
    with pytest.raises(MultiDwellInputError, match="truncated"):
        replace(bank, source_candidate_count=3)
    shortened = replace(
        bank.candidates[0],
        dwell_predictions=bank.candidates[0].dwell_predictions[:-1],
    )
    with pytest.raises(MultiDwellInputError, match="exact ordered dwell"):
        replace(bank, candidates=(shortened, bank.candidates[1]))
    assert tuple(item.dwell_id for item in dwells) == bank.dwell_ids


def test_invalid_numeric_inputs_and_ill_conditioned_score_fail_closed() -> None:
    with pytest.raises(MultiDwellInputError, match="finite"):
        SyntheticCfoDwell(
            dwell_id="bad",
            center_utc_ns=_BASE_UTC_NS,
            hardware_epoch_id="epoch-a",
            support_offsets_s=(-1.0, 1.0),
            measured_cfo_hz=(0.0, math.nan),
            measurement_standard_uncertainties_hz=(1.0, 1.0),
        )
    with pytest.raises(MultiDwellInputError, match="positive"):
        _config(dwell_offset_prior_standard_uncertainty_hz=0.0)
    with pytest.raises(MultiDwellNumericalError, match="condition bound"):
        marginalize_dwell_nuisance(
            (0.0, 0.0),
            (-1.0, 1.0),
            (1.0, 2.0),
            drift_prior_mean_hz_per_s=0.0,
            drift_prior_standard_uncertainty_hz_per_s=1.0,
            dwell_offset_prior_standard_uncertainty_hz=1.0,
            maximum_condition_number=1.0,
        )
    with pytest.raises(MultiDwellNumericalError, match="variance is not representable"):
        marginalize_dwell_nuisance(
            (0.0, 0.0),
            (-1.0, 1.0),
            (1.0, 1.0),
            drift_prior_mean_hz_per_s=0.0,
            drift_prior_standard_uncertainty_hz_per_s=1e308,
            dwell_offset_prior_standard_uncertainty_hz=1.0,
        )
    with pytest.raises(MultiDwellNumericalError, match="variance is not representable"):
        marginalize_dwell_nuisance(
            (0.0, 0.0),
            (-1.0, 1.0),
            (1.0, 1.0),
            drift_prior_mean_hz_per_s=0.0,
            drift_prior_standard_uncertainty_hz_per_s=1.0,
            dwell_offset_prior_standard_uncertainty_hz=1e308,
        )
    with pytest.raises(MultiDwellInputError, match="signed 64-bit UTC"):
        replace(
            SyntheticCfoDwell(
                dwell_id="bounded-time",
                center_utc_ns=_BASE_UTC_NS,
                hardware_epoch_id="epoch-a",
                support_offsets_s=(-1.0, 1.0),
                measured_cfo_hz=(0.0, 0.0),
                measurement_standard_uncertainties_hz=(1.0, 1.0),
            ),
            center_utc_ns=10**400,
        )


def test_huge_random_walk_scale_and_response_access_poison_fail_closed() -> None:
    dwells, bank = _fixture((101, 101))
    with pytest.raises(MultiDwellNumericalError, match="variance is not representable"):
        filter_multi_dwell_catalogue_modes(
            dwells,
            bank,
            config=_config(drift_random_walk_standard_uncertainty_hz_per_s_per_sqrt_s=1e308),
        )

    object.__setattr__(bank, "response_accessed", True)
    with pytest.raises(MultiDwellInputError, match="response-free"):
        filter_multi_dwell_catalogue_modes(dwells, bank, config=_config())

    tau_dwells, tau_bank = _fixture((101, 101))
    object.__setattr__(tau_bank, "tau_policy", "response-profiled")
    with pytest.raises(MultiDwellInputError, match="fixed precomputed tau"):
        filter_multi_dwell_catalogue_modes(tau_dwells, tau_bank, config=_config())


def test_extreme_common_log_weight_translation_is_stable_but_range_overflow_fails() -> None:
    dwells, bank = _fixture((101,))
    stable = filter_multi_dwell_catalogue_modes(
        dwells,
        bank,
        config=_config(
            initial_null_log_weight=1e308,
            initial_candidate_log_weight=1e308,
        ),
    )
    assert math.fsum(
        item.posterior_probability_within_retained_beam for item in stable.final_modes
    ) == pytest.approx(1.0)

    with pytest.raises(MultiDwellNumericalError, match="range"):
        filter_multi_dwell_catalogue_modes(
            dwells,
            bank,
            config=_config(
                initial_null_log_weight=1e308,
                initial_candidate_log_weight=-1e308,
            ),
        )


def test_work_bound_fails_before_any_dwell_score(monkeypatch: pytest.MonkeyPatch) -> None:
    dwells, bank = _fixture((101,))
    calls = 0

    def forbidden_score(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        raise AssertionError("work bound must fail before response scoring")

    monkeypatch.setattr(smoothing_module, "marginalize_dwell_nuisance", forbidden_score)
    with pytest.raises(MultiDwellWorkLimitError, match="before scoring"):
        filter_multi_dwell_catalogue_modes(
            dwells,
            bank,
            config=_config(maximum_evaluated_extensions=2),
        )
    assert calls == 0

    with pytest.raises(MultiDwellWorkLimitError, match="maximum_support_rows_per_dwell"):
        filter_multi_dwell_catalogue_modes(
            dwells,
            bank,
            config=_config(maximum_support_rows_per_dwell=3),
        )
    with pytest.raises(MultiDwellWorkLimitError, match="maximum_evaluated_support_rows"):
        filter_multi_dwell_catalogue_modes(
            dwells,
            bank,
            config=_config(maximum_evaluated_support_rows=11),
        )
    assert calls == 0


def test_unrepresentable_nonzero_path_increment_fails_instead_of_reporting_zero() -> None:
    dwells, bank = _fixture((None, None))
    huge_first = replace(
        dwells[0],
        measured_cfo_hz=(1e150, -1e150, -1e150, 1e150),
    )

    with pytest.raises(MultiDwellNumericalError, match="loses a nonzero increment"):
        filter_multi_dwell_catalogue_modes(
            (huge_first, dwells[1]),
            bank,
            config=_config(),
        )


def test_frozen_inputs_and_pure_analyzer_boundary() -> None:
    dwells, bank = _fixture((101,))
    with pytest.raises(FrozenInstanceError):
        dwells[0].dwell_id = "changed"  # type: ignore[misc]

    source_path = Path(smoothing_module.__file__ or "")
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert imported.isdisjoint({"fastapi", "psycopg", "sqlalchemy", "requests", "httpx", "typer"})
    assert not any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open"
        for node in ast.walk(tree)
    )

    result = filter_multi_dwell_catalogue_modes(dwells, bank, config=_config())
    assert result.nuisance_scope == "receiver-local-nontransferable-v1"
    assert not result.nuisance_transferable_to_satellite_frequency_state_v1
