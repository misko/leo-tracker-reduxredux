from __future__ import annotations

import math
from dataclasses import asdict

import numpy as np
import pytest

from leo.analysis import catalogue_observability as observability_module
from leo.analysis.catalogue_observability import (
    CandidateObservabilityConfig,
    CatalogueObservabilityInputError,
    CatalogueObservabilityWorkLimitError,
    MeasurementFloorOverlay,
    ObservabilityWorkLimits,
    WrongFieldBankExpectation,
    analyze_candidate_observability,
    candidate_observability_result_payload,
)
from leo.analysis.catalogue_prediction_array_view import (
    catalogue_prediction_array_view_from_bank,
)
from leo.contracts.catalogue_association import (
    CandidateObservationPredictionV1,
    CandidateTauStateV1,
    CatalogueCandidatePredictionV1,
    CataloguePredictionBankV1,
    CataloguePredictionSupportObservationV1,
    CataloguePredictionSupportV1,
    CatalogueVerifiedTleMemberV1,
)
from leo.contracts.digests import canonical_digest
from leo.contracts.sky import ObserverSiteV1, TleSnapshotRefV1


def _support(count: int = 6) -> CataloguePredictionSupportV1:
    episode = canonical_digest({"episode": "response-free-observability"})
    rows = tuple(
        CataloguePredictionSupportObservationV1(
            observation_id=canonical_digest({"observation": index}),
            episode_id=episode,
            support_start_utc_ns=2_000_000_000_000_000_000 + index * 1_000_000_000,
            support_center_utc_ns=(2_000_000_000_000_100_000 + index * 1_000_000_000),
            support_end_utc_ns=2_000_000_000_000_200_000 + index * 1_000_000_000,
            factorial_support_moments_s=(1.0, 0.0, 1e-9, 0.0),
        )
        for index in range(count)
    )
    payload = {
        "schema_version": 1,
        "algorithm_version": "catalogue-prediction-support-v1",
        "episode_ids": (episode,),
        "observations": tuple(item.model_dump(mode="json") for item in rows),
        "response_fields_excluded": True,
    }
    return CataloguePredictionSupportV1.model_validate(
        {**payload, "content_digest": canonical_digest(payload)}
    )


def _bank(
    support: CataloguePredictionSupportV1,
    curves: dict[int, tuple[float, ...]],
    *,
    field: int,
    tau_shift_scale: float = 0.2,
    tau_curves: dict[int, dict[float, tuple[float, ...]]] | None = None,
) -> CataloguePredictionBankV1:
    episode = support.episode_ids[0]
    prediction_reference_utc_ns = min(item.support_center_utc_ns for item in support.observations)
    observation_ids = tuple(
        item.observation_id
        for item in sorted(support.observations, key=lambda item: item.observation_id)
    )
    by_id_index = {
        item.observation_id: index
        for index, item in enumerate(
            sorted(support.observations, key=lambda row: row.support_center_utc_ns)
        )
    }
    candidates = []
    members = []
    for catalog_number, curve in sorted(curves.items()):
        element_digest = canonical_digest({"element": catalog_number, "field": field})
        epoch = 1_999_000_000_000_000_000 + catalog_number
        states = []
        for tau_s in (-5.0, 0.0, 5.0):
            overridden_curve = (
                None if tau_curves is None else tau_curves.get(catalog_number, {}).get(tau_s)
            )
            predictions = tuple(
                CandidateObservationPredictionV1(
                    observation_id=observation_id,
                    predicted_cfo_hz=(
                        overridden_curve[by_id_index[observation_id]]
                        if overridden_curve is not None
                        else curve[by_id_index[observation_id]]
                        + tau_s * tau_shift_scale * by_id_index[observation_id] ** 2
                    ),
                    standard_uncertainty_hz=1.0,
                )
                for observation_id in observation_ids
            )
            states.append(
                CandidateTauStateV1(
                    tau_s=tau_s,
                    log_prior_weight=0.0,
                    predictions=predictions,
                )
            )
        candidates.append(
            CatalogueCandidatePredictionV1(
                catalog_number=catalog_number,
                object_name=f"STARLINK-{catalog_number}",
                selected_element_digest=element_digest,
                element_epoch_utc_ns=epoch,
                element_age_s_at_reference=(abs(prediction_reference_utc_ns - epoch) / 1e9),
                eligible_episode_ids=(episode,),
                tau_states=tuple(states),
            )
        )
        members.append(
            CatalogueVerifiedTleMemberV1(
                catalog_number=catalog_number,
                selected_element_digest=element_digest,
                element_epoch_utc_ns=epoch,
            )
        )
    snapshot = TleSnapshotRefV1(
        provider="space-track",
        collected_utc_ns=min(item.support_start_utc_ns for item in support.observations)
        - 1_000_000_000,
        digest=canonical_digest({"snapshot": "observability"}),
        object_count=100,
    )
    return CataloguePredictionBankV1.create(
        support=support,
        tle_snapshot=snapshot,
        observer_site=ObserverSiteV1(
            latitude_deg=37.8,
            longitude_deg=-122.4,
            altitude_m=10.0,
            label="known-test-site",
        ),
        nominal_rf_hz=11_440_312_498.0,
        selection_protocol_digest=canonical_digest({"protocol": "observability"}),
        selection_policy_digest=canonical_digest({"field": field}),
        tle_membership_authority_digest=canonical_digest(
            {"membership": field, "numbers": sorted(curves)}
        ),
        verified_tle_members=tuple(members),
        propagation_model="test-sgp4-v1",
        candidates=tuple(candidates),
        source_candidate_count=len(candidates),
        tau_search_policy="bounded-profile-minus5-plus5-v1",
    )


def _inputs() -> tuple[
    CataloguePredictionBankV1,
    tuple[CataloguePredictionBankV1, CataloguePredictionBankV1],
]:
    support = _support()
    shape = np.asarray((0.0, 1.0, 0.0, -1.0, 0.0, 1.0))
    true = _bank(
        support,
        {
            10_001: tuple(np.zeros(6)),
            10_002: tuple(shape),
            10_003: tuple(2.0 * shape),
            10_004: tuple(20.0 * np.arange(6) + 500.0),
        },
        field=0,
    )
    minus = _bank(
        support,
        {
            10_001: tuple(np.zeros(6) + 700.0),
            20_001: tuple(shape * 1.05 + 200.0),
            20_002: tuple(3.0 * shape),
        },
        field=-500,
    )
    plus = _bank(
        support,
        {
            10_003: tuple(2.2 * shape - 300.0),
            30_001: tuple(0.1 * shape + 100.0),
            30_002: tuple(4.0 * shape),
        },
        field=500,
    )
    return true, (minus, plus)


def _config(
    true: CataloguePredictionBankV1,
    wrong: tuple[CataloguePredictionBankV1, CataloguePredictionBankV1],
    *,
    floors: tuple[MeasurementFloorOverlay, ...] | None = None,
    work_limits: ObservabilityWorkLimits | None = None,
    neighbours: int = 3,
) -> CandidateObservabilityConfig:
    selected_floors = (
        (
            MeasurementFloorOverlay(
                history_ms=20.0,
                floor_hz=0.8,
                source_digest=canonical_digest({"floor": 20}),
            ),
            MeasurementFloorOverlay(
                history_ms=125.0,
                floor_hz=1.1,
                source_digest=canonical_digest({"floor": 125}),
            ),
            MeasurementFloorOverlay(
                history_ms=500.0,
                floor_hz=1.5,
                source_digest=canonical_digest({"floor": 500}),
            ),
        )
        if floors is None
        else floors
    )
    return CandidateObservabilityConfig(
        expected_true_field_bank_digest=true.content_digest,
        expected_wrong_field_banks=(
            WrongFieldBankExpectation(-500, wrong[0].content_digest),
            WrongFieldBankExpectation(500, wrong[1].content_digest),
        ),
        expected_support_digest=true.support.content_digest,
        expected_tle_snapshot_digest=true.tle_snapshot.digest,
        close_pair_neighbours_per_candidate=neighbours,
        floor_overlays=selected_floors,
        work_limits=work_limits or ObservabilityWorkLimits(),
    )


def _run(**kwargs: object):  # type: ignore[no-untyped-def]
    true, wrong = _inputs()
    config = _config(true, wrong, **kwargs)
    return analyze_candidate_observability(
        true_field_bank=true,
        wrong_field_banks=wrong,
        config=config,
    )


def test_atlas_is_response_free_complete_and_digest_closed() -> None:
    result = _run()

    assert result.measured_response_accessed is False
    assert result.candidate_universe_selected_from_response is False
    assert result.identity_claimed is False
    assert result.numerical_thresholds_frozen is False
    assert result.wrong_epoch_is_gate is False
    assert result.candidate_numbers == (10_001, 10_002, 10_003, 10_004)
    assert tuple(item.nuisance_model for item in result.nuisance_geometries) == (
        "offset-only-v1",
        "offset-plus-ridge-drift-v1",
    )
    assert all(
        item.distance_covariance_model == "homoscedastic-identity-rms-v1"
        for item in result.nuisance_geometries
    )
    assert len(result.nuisance_geometries[0].prefix_summaries) == 6
    assert len(result.nuisance_geometries[0].floor_overlays) == 3
    assert len(result.nuisance_geometries[1].floor_overlays) == 3
    assert result.work_receipt.tau_state_count == 3
    assert result.work_receipt.close_pair_count == 6
    assert result.work_receipt.profiled_tau_pair_distance_matrix_count == 6
    assert result.work_receipt.profiled_tau_pair_observation_evaluations == 576
    profiled = result.profiled_tau_candidate_identity_atlas
    assert profiled.complete_tau_cross_product_evaluated is True
    assert profiled.measured_response_accessed is False
    assert profiled.candidate_universe_selected_from_response is False
    assert profiled.identity_claimed is False
    assert profiled.tau_values_s == (-5.0, 0.0, 5.0)
    assert len(profiled.floor_neighborhoods) == 3
    profiled_document = asdict(profiled)
    profiled_digest = profiled_document.pop("content_digest")
    assert profiled_digest == canonical_digest(profiled_document)
    assert candidate_observability_result_payload(result)["content_digest"] == (
        result.content_digest
    )


def test_pure_array_view_is_numerically_and_digest_identical() -> None:
    true, wrong = _inputs()
    expected = analyze_candidate_observability(
        true_field_bank=true,
        wrong_field_banks=wrong,
        config=_config(true, wrong),
    )
    true_view = catalogue_prediction_array_view_from_bank(true, field_delta_s=0)
    wrong_views = (
        catalogue_prediction_array_view_from_bank(wrong[0], field_delta_s=-500),
        catalogue_prediction_array_view_from_bank(wrong[1], field_delta_s=500),
    )

    observed = analyze_candidate_observability(
        true_field_bank=true_view,
        wrong_field_banks=wrong_views,
        config=_config(true, wrong),
    )

    assert observed == expected
    true_view.predicted_cfo_hz.setflags(write=True)
    with pytest.raises(
        CatalogueObservabilityInputError,
        match="true-time prediction bank is invalid",
    ):
        analyze_candidate_observability(
            true_field_bank=true_view,
            wrong_field_banks=wrong_views,
            config=_config(true, wrong),
        )


def test_offset_and_ridge_drift_match_direct_dense_least_squares() -> None:
    result = _run()
    curves = {
        (item.left_catalog_number, item.right_catalog_number): item
        for item in result.nuisance_geometries[0].close_pair_curves
    }
    offset_curve = curves[(10_001, 10_004)]
    # Candidate 10004 differs only by offset + linear rate, so offset-only leaves rate.
    x = 20.0 * np.arange(6) + 500.0
    design_offset = np.ones((6, 1))
    residual = x - design_offset @ np.linalg.lstsq(design_offset, x, rcond=None)[0]
    assert offset_curve.projected_rms_hz_by_prefix[-1] == pytest.approx(
        math.sqrt(float(residual @ residual) / 6)
    )

    drift_curves = {
        (item.left_catalog_number, item.right_catalog_number): item
        for item in result.nuisance_geometries[1].close_pair_curves
    }
    design = np.column_stack((np.ones(6), np.arange(6, dtype=float)))
    penalty = np.diag((0.0, (50.0 / 20.0) ** 2))
    beta = np.linalg.solve(design.T @ design + penalty, design.T @ x)
    objective = float((x - design @ beta) @ (x - design @ beta) + beta @ penalty @ beta)
    assert drift_curves[(10_001, 10_004)].projected_rms_hz_by_prefix[-1] == (
        pytest.approx(math.sqrt(objective / 6))
    )
    assert (
        drift_curves[(10_001, 10_004)].projected_rms_hz_by_prefix[-1]
        < (offset_curve.projected_rms_hz_by_prefix[-1])
    )


def test_offset_projection_is_stable_at_absolute_cfo_scale() -> None:
    small = np.asarray(
        (
            (0.0, 1.0, 4.0, 9.0, 16.0, 25.0),
            (0.0, 1.2, 4.3, 9.5, 16.8, 26.0),
            (0.0, -0.8, -3.5, -8.2, -14.9, -23.6),
        ),
        dtype=np.float64,
    )
    large = small + np.asarray((1.2e9, -8.7e8, 4.4e9))[:, None]
    times_s = np.arange(small.shape[1], dtype=np.float64)
    spec = observability_module._NuisanceSpec(
        name="offset-only-v1",
        drift_ridge_s2=None,
    )

    expected = observability_module._within_distance_matrix(
        small,
        times_s,
        spec,
        1e-6,
    )
    observed = observability_module._within_distance_matrix(
        large,
        times_s,
        spec,
        1e-6,
    )

    assert observed == pytest.approx(expected, abs=2e-7)


def test_single_linkage_reports_chaining_and_local_soft_counts() -> None:
    result = _run()
    overlay = next(
        item for item in result.nuisance_geometries[0].floor_overlays if item.floor_hz == 1.1
    )
    component = next(item for item in overlay.final_components if 10_001 in item.catalog_numbers)
    assert component.catalog_numbers == (10_001, 10_002, 10_003)
    assert component.chained is True
    assert component.relationship == "single-linkage-connected-neighborhood-v1"
    by_number = {item.catalog_number: item for item in overlay.final_candidate_summaries}
    assert by_number[10_002].local_candidate_count == 3
    assert by_number[10_001].local_candidate_count == 2
    assert 1.0 < by_number[10_001].soft_effective_candidate_count < 3.0
    assert overlay.prefix_summaries[-1].chained_component_count == 1


def test_profiled_tau_identity_atlas_joins_reverse_assignment_cross_tau_witness() -> None:
    support = _support()
    index = np.arange(6, dtype=np.float64)
    common = 275_000.0 * np.sin(index / 2.3) + 20_000.0 * np.cos(index / 0.71)
    shape = np.asarray((0.0, 1.0, 0.0, -1.0, 0.0, 1.0))
    true = _bank(
        support,
        {
            10_001: tuple(common),
            10_002: tuple(common + 100.0 * shape),
        },
        field=0,
        tau_curves={
            10_001: {
                -5.0: tuple(common + 1_000.0 * shape + 300_000.0),
                0.0: tuple(common + 120_000.0),
                5.0: tuple(common + 500.0 * shape - 80_000.0),
            },
            10_002: {
                -5.0: tuple(common + 500.0 * shape + 500_000.0),
                0.0: tuple(common + 100.0 * shape - 200_000.0),
                5.0: tuple(common - 1_000.0 * shape + 100_000.0),
            },
        },
    )
    minus = _bank(
        support,
        {20_001: tuple(common), 20_002: tuple(common + 2_000.0 * shape)},
        field=-500,
        tau_shift_scale=0.0,
    )
    plus = _bank(
        support,
        {30_001: tuple(common), 30_002: tuple(common - 2_000.0 * shape)},
        field=500,
        tau_shift_scale=0.0,
    )
    floor = MeasurementFloorOverlay(
        history_ms=125.0,
        floor_hz=1.0,
        source_digest=canonical_digest({"floor": "profiled-tau-witness"}),
    )

    data = observability_module._bank_data(  # noqa: SLF001
        catalogue_prediction_array_view_from_bank(true, field_delta_s=0),
        include_all_tau=True,
    )
    drift = observability_module._NuisanceSpec(  # noqa: SLF001
        observability_module._DRIFT_MODEL,  # noqa: SLF001
        (50.0 / 20.0) ** 2,
    )
    cross = observability_module._cross_distance_matrix(  # noqa: SLF001
        data.predictions_by_tau[-5.0],
        data.predictions_by_tau[5.0],
        data.times_s,
        drift,
        1e-6,
    )
    assert cross[0, 1] > floor.floor_hz
    assert cross[1, 0] < floor.floor_hz

    result = analyze_candidate_observability(
        true_field_bank=true,
        wrong_field_banks=(minus, plus),
        config=_config(true, (minus, plus), floors=(floor,), neighbours=1),
    )

    tau_zero = result.nuisance_geometries[1].floor_overlays[0]
    assert tuple(item.catalog_numbers for item in tau_zero.final_components) == (
        (10_001,),
        (10_002,),
    )
    profiled = result.profiled_tau_candidate_identity_atlas.floor_neighborhoods[0]
    assert profiled.candidate_identity_edge_count == 1
    assert profiled.component_count == 1
    assert profiled.final_components[0].catalog_numbers == (10_001, 10_002)
    assert profiled.final_components[0].diameter_rms_hz < 1e-8


def test_close_pairs_are_causal_and_crossings_distinguish_first_from_persistent() -> None:
    result = _run(neighbours=3)
    primary = result.nuisance_geometries[0]
    curve = next(
        item
        for item in primary.close_pair_curves
        if (item.left_catalog_number, item.right_catalog_number) == (10_001, 10_003)
    )
    assert curve.selected_response_free is True
    assert curve.projected_rms_hz_by_prefix[0] == 0.0
    overlay = next(item for item in primary.floor_overlays if item.floor_hz == 1.1)
    curve_index = primary.close_pair_curves.index(curve)
    crossing = overlay.close_pair_crossings[curve_index]
    assert crossing.first_above_prefix_index is not None
    assert crossing.persistent_above_prefix_index is not None
    assert crossing.persistent_above_prefix_index >= crossing.first_above_prefix_index


def test_tau_and_wrong_epoch_are_separate_and_wrong_fields_are_observe_only() -> None:
    result = _run()
    assert len(result.tau_sensitivity) == 4
    assert all(
        tuple(item.tau_s for item in candidate.states_relative_to_tau_zero) == (-5.0, 5.0)
        for candidate in result.tau_sensitivity
    )
    assert result.tau_prefix_summaries[0].maximum_candidate_max_tau_rms_hz == 0.0
    assert result.tau_prefix_summaries[-1].maximum_candidate_max_tau_rms_hz > 0.0
    assert tuple(item.field_delta_s for item in result.wrong_field_observability) == (
        -500,
        500,
    )
    for field in result.wrong_field_observability:
        assert field.true_field_tau_s == 0.0
        assert field.comparison_field_tau_s == 0.0
        assert field.tau_profiled is False
        assert field.observe_only is True
        assert field.p_value_computed is False
        assert field.identity_gate_applied is False
        assert len(field.final_candidate_alternatives) == 4
        assert len(field.prefix_summaries) == 6
    minus = result.wrong_field_observability[0]
    first = next(
        item
        for item in minus.final_candidate_alternatives
        if item.true_field_catalog_number == 10_001
    )
    # Constant offsets are removed, so same-NORAD 10001 is an exact wrong-field mimic.
    assert first.nearest_any_catalog_number == 10_001
    assert first.nearest_any_final_rms_hz == pytest.approx(0.0)
    assert first.nearest_different_norad_catalog_number == 20_001


def test_floor_overlay_is_detachable_from_response_free_geometry_digest() -> None:
    true, wrong = _inputs()
    first = analyze_candidate_observability(
        true_field_bank=true,
        wrong_field_banks=wrong,
        config=_config(true, wrong),
    )
    changed_floor = (
        MeasurementFloorOverlay(
            history_ms=125.0,
            floor_hz=50.0,
            source_digest=canonical_digest({"different": "floor"}),
        ),
    )
    second = analyze_candidate_observability(
        true_field_bank=true,
        wrong_field_banks=wrong,
        config=_config(true, wrong, floors=changed_floor),
    )

    assert first.response_free_geometry_digest == second.response_free_geometry_digest
    assert first.config_digest != second.config_digest
    assert first.content_digest != second.content_digest
    assert (
        first.profiled_tau_candidate_identity_atlas.content_digest
        != second.profiled_tau_candidate_identity_atlas.content_digest
    )
    assert first.nuisance_geometries[0].close_pair_curves == (
        second.nuisance_geometries[0].close_pair_curves
    )


def test_suffix_prediction_change_cannot_change_earlier_prefix_geometry() -> None:
    true, wrong = _inputs()
    original = analyze_candidate_observability(
        true_field_bank=true,
        wrong_field_banks=wrong,
        config=_config(true, wrong, neighbours=3),
    )
    changed_curves = {
        candidate.catalog_number: tuple(
            next(state for state in candidate.tau_states if state.tau_s == 0.0)
            .predictions[index]
            .predicted_cfo_hz
            for index in range(6)
        )
        for candidate in true.candidates
    }
    # Rebuild from the support-time curves; only the last two points of one candidate change.
    chronology = tuple(
        item.observation_id
        for item in sorted(true.support.observations, key=lambda row: row.support_center_utc_ns)
    )
    candidate = next(item for item in true.candidates if item.catalog_number == 10_003)
    state = next(item for item in candidate.tau_states if item.tau_s == 0.0)
    by_id = {item.observation_id: item.predicted_cfo_hz for item in state.predictions}
    curve = [by_id[item] for item in chronology]
    curve[-2:] = [item + 100.0 for item in curve[-2:]]
    changed_curves[10_003] = tuple(curve)
    # Normalize all other curves to chronology as well.
    for item in true.candidates:
        if item.catalog_number == 10_003:
            continue
        state = next(value for value in item.tau_states if value.tau_s == 0.0)
        values = {value.observation_id: value.predicted_cfo_hz for value in state.predictions}
        changed_curves[item.catalog_number] = tuple(values[key] for key in chronology)
    changed_true = _bank(true.support, changed_curves, field=0)
    changed = analyze_candidate_observability(
        true_field_bank=changed_true,
        wrong_field_banks=wrong,
        config=_config(changed_true, wrong, neighbours=3),
    )
    original_by_pair = {
        (item.left_catalog_number, item.right_catalog_number): item
        for item in original.nuisance_geometries[0].close_pair_curves
    }
    changed_by_pair = {
        (item.left_catalog_number, item.right_catalog_number): item
        for item in changed.nuisance_geometries[0].close_pair_curves
    }
    common = set(original_by_pair) & set(changed_by_pair)
    assert common
    for pair in common:
        assert original_by_pair[pair].projected_rms_hz_by_prefix[:4] == pytest.approx(
            changed_by_pair[pair].projected_rms_hz_by_prefix[:4]
        )


def test_large_common_cfo_trend_uses_stable_pair_differences() -> None:
    support = _support(128)
    times_s = np.linspace(0.0, 30.0, 128)
    common = 275_000.0 * np.sin(2.0 * np.pi * times_s / 53.0) + 20_000.0 * np.sin(
        2.0 * np.pi * times_s / 7.3
    )
    tiny_difference = 0.01 * np.sin(2.0 * np.pi * times_s / 11.1) + 0.0037 * np.cos(
        2.0 * np.pi * times_s / 3.7
    )
    true = _bank(
        support,
        {
            10_001: tuple(common + 120_000.0),
            10_002: tuple(common + tiny_difference - 80_000.0),
        },
        field=0,
        tau_shift_scale=0.0,
    )
    minus = _bank(
        support,
        {
            20_001: tuple(common + tiny_difference + 500_000.0),
            20_002: tuple(common + 50.0 * np.sin(times_s) + 300_000.0),
        },
        field=-500,
        tau_shift_scale=0.0,
    )
    plus = _bank(
        support,
        {
            30_001: tuple(common - tiny_difference - 400_000.0),
            30_002: tuple(common + 60.0 * np.cos(times_s) - 200_000.0),
        },
        field=500,
        tau_shift_scale=0.0,
    )

    result = analyze_candidate_observability(
        true_field_bank=true,
        wrong_field_banks=(minus, plus),
        config=_config(true, (minus, plus), floors=(), neighbours=1),
    )

    difference = (common + 120_000.0) - (common + tiny_difference - 80_000.0)
    expected_curve = tuple(
        math.sqrt(float(np.mean((difference[:count] - np.mean(difference[:count])) ** 2)))
        for count in range(1, len(difference) + 1)
    )
    assert result.nuisance_geometries[0].close_pair_curves[
        0
    ].projected_rms_hz_by_prefix == pytest.approx(expected_curve, abs=1e-9)
    for field in result.wrong_field_observability:
        assert field.final_candidate_alternatives[0].nearest_any_final_rms_hz == pytest.approx(
            expected_curve[-1],
            abs=1e-9,
        )


def test_tau_direct_curve_is_stable_when_a_removable_offset_dominates() -> None:
    times_s = np.linspace(0.0, 30.0, 256)
    difference = 200_000.0 + 0.01 * np.sin(times_s / 2.3) + 0.004 * np.cos(times_s / 0.71)
    primary = observability_module._NuisanceSpec(  # noqa: SLF001
        observability_module._PRIMARY_MODEL,  # noqa: SLF001
        None,
    )
    drift = observability_module._NuisanceSpec(  # noqa: SLF001
        observability_module._DRIFT_MODEL,  # noqa: SLF001
        (50.0 / 20.0) ** 2,
    )

    primary_curve = observability_module._direct_pair_curve(  # noqa: SLF001
        difference,
        times_s,
        primary,
        1e-6,
    )
    expected_primary = tuple(
        math.sqrt(float(np.mean((difference[:count] - np.mean(difference[:count])) ** 2)))
        for count in range(1, len(difference) + 1)
    )
    assert primary_curve == pytest.approx(expected_primary, abs=1e-9)

    drift_curve = observability_module._direct_pair_curve(  # noqa: SLF001
        difference,
        times_s,
        drift,
        1e-6,
    )
    design = np.column_stack((np.ones(len(times_s)), times_s))
    penalty = np.diag((0.0, (50.0 / 20.0) ** 2))
    beta = np.linalg.solve(design.T @ design + penalty, design.T @ difference)
    residual = difference - design @ beta
    objective = float(residual @ residual + beta @ penalty @ beta)
    assert drift_curve[-1] == pytest.approx(
        math.sqrt(objective / len(times_s)),
        abs=1e-9,
    )


def test_close_pair_union_covers_each_nuisance_geometry_and_caps_once() -> None:
    candidates = np.asarray((10_001, 10_002, 10_003, 10_004), dtype=np.int64)
    primary = np.asarray(
        (
            (0.0, 1.0, 8.0, 9.0),
            (1.0, 0.0, 9.0, 8.0),
            (8.0, 9.0, 0.0, 1.0),
            (9.0, 8.0, 1.0, 0.0),
        )
    )
    drift = np.asarray(
        (
            (0.0, 8.0, 1.0, 9.0),
            (8.0, 0.0, 9.0, 1.0),
            (1.0, 9.0, 0.0, 8.0),
            (9.0, 1.0, 8.0, 0.0),
        )
    )

    pairs = observability_module._select_close_pairs(  # noqa: SLF001
        (primary, drift),
        candidates,
        neighbours=1,
        maximum_pairs=4,
    )

    assert pairs == ((0, 1), (0, 2), (1, 3), (2, 3))
    with pytest.raises(CatalogueObservabilityWorkLimitError, match="close-pair set"):
        observability_module._select_close_pairs(  # noqa: SLF001
            (primary, drift),
            candidates,
            neighbours=1,
            maximum_pairs=3,
        )


def test_digest_support_and_work_cap_poisons_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    true, wrong = _inputs()
    bad_config = _config(true, wrong)
    bad_config = CandidateObservabilityConfig(
        expected_true_field_bank_digest=canonical_digest({"wrong": "bank"}),
        expected_wrong_field_banks=bad_config.expected_wrong_field_banks,
        expected_support_digest=bad_config.expected_support_digest,
        expected_tle_snapshot_digest=bad_config.expected_tle_snapshot_digest,
        floor_overlays=bad_config.floor_overlays,
    )
    with pytest.raises(CatalogueObservabilityInputError, match="true-field"):
        analyze_candidate_observability(
            true_field_bank=true, wrong_field_banks=wrong, config=bad_config
        )

    tiny = ObservabilityWorkLimits(maximum_pair_prefix_evaluations=1)

    def allocation_poison(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("prediction matrices were allocated before work-cap preflight")

    monkeypatch.setattr(observability_module, "_bank_data", allocation_poison)
    with pytest.raises(CatalogueObservabilityWorkLimitError, match="pair-prefix"):
        analyze_candidate_observability(
            true_field_bank=true,
            wrong_field_banks=wrong,
            config=_config(true, wrong, work_limits=tiny),
        )

    poisoned = true.model_copy(update={"content_digest": canonical_digest({"tampered": True})})
    with pytest.raises(CatalogueObservabilityInputError, match="prediction bank is invalid"):
        analyze_candidate_observability(
            true_field_bank=poisoned,
            wrong_field_banks=wrong,
            config=_config(true, wrong),
        )


def test_profiled_tau_work_cap_fails_before_prediction_matrix_allocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    true, wrong = _inputs()
    limits = ObservabilityWorkLimits(
        maximum_profiled_tau_pair_observation_evaluations=575,
    )

    def allocation_poison(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("prediction matrices were allocated before profiled-tau preflight")

    monkeypatch.setattr(observability_module, "_bank_data", allocation_poison)
    with pytest.raises(CatalogueObservabilityWorkLimitError, match="profiled-tau"):
        analyze_candidate_observability(
            true_field_bank=true,
            wrong_field_banks=wrong,
            config=_config(true, wrong, work_limits=limits),
        )
