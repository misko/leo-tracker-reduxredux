from __future__ import annotations

import math
from dataclasses import replace

import numpy as np
import pytest

from leo.analysis.research.doppler_holdout_pre_response import (
    DEFAULT_STRICT_PAST_CONFIGS,
    PREDICTION_LEDGER_SCHEMA,
    DopplerHoldoutPredictionLedgerV1,
    ForecastTargetKeyV1,
    PredictionLedgerRowV1,
    StrictPastForecastV1,
)
from leo.analysis.research.doppler_holdout_response_v2 import (
    ODD_ATTACHMENT_SCHEMA_V2,
    OddQinAttachmentLedgerV2,
    OddQinAttachmentRowV2,
    OddQinResponseMeasurementV2,
)
from leo.analysis.research.final_doppler_holdout import (
    BASELINE_ASSOCIATION_METHOD,
    PRIMARY_ASSOCIATION_METHOD,
    ROLLING_ORIGIN_TRAINING_FRACTIONS,
    WITHIN_TRACK_PERMUTATION_COUNT,
    WITHIN_TRACK_PERMUTATION_SEED,
    FrozenOddBinResponse,
    fit_shared_radio_rate_sensitivity,
    freeze_association_bins,
    freeze_candidate_ranking,
    freeze_rolling_origin_controls,
    freeze_within_track_permutation_controls,
    frozen_wrong_time_offsets_s,
    quadratic_promotion_gate,
    score_forecasts,
    score_frozen_candidate_ranking,
    validate_frozen_candidate_ranking,
)
from leo.contracts.digests import canonical_digest

DIGEST = "sha256:" + "1" * 64
OTHER_DIGEST = "sha256:" + "2" * 64
RATE_HZ = 1_000


def _forecast(
    method_index: int,
    *,
    target_reference: float,
    predicted: float,
    complete: bool,
) -> StrictPastForecastV1:
    config = DEFAULT_STRICT_PAST_CONFIGS[method_index]
    common = {
        "method": config.name,
        "history_s": config.history_s,
        "polynomial_degree": config.polynomial_degree,
        "history_frame_count": 30 if complete else 0,
        "history_span_ms": config.history_s * 1_000 if complete else 0.0,
        "history_to_target_span_ms": config.history_s * 1_000 if complete else 0.0,
        "maximum_gap_ms": 2.0 if complete else 0.0,
        "history_digest": DIGEST,
    }
    if not complete:
        return StrictPastForecastV1.model_validate(
            {**common, "status": "no_result", "rejection_reasons": ("insufficient_history",)}
        )
    return StrictPastForecastV1.model_validate(
        {
            **common,
            "status": "complete",
            "rejection_reasons": (),
            "effective_history_frame_count": 25.0,
            "earliest_history_reference_sample": target_reference - 500.0,
            "latest_history_reference_sample": target_reference - 1.0,
            "predicted_cfo_hz": predicted,
            "rate_hz_s": -2_000.0,
            "acceleration_hz_s2": 100.0 if config.polynomial_degree == 2 else 0.0,
            "weighted_rms_hz": 30.0,
            "converged": True,
        }
    )


def _ledger(
    session_counts: dict[str, int],
    *,
    incomplete_prefix: int = 0,
    baseline_error_hz: float = 20.0,
    quadratic_error_hz: float = 5.0,
    spacing_samples: int = 20,
) -> DopplerHoldoutPredictionLedgerV1:
    rows: list[PredictionLedgerRowV1] = []
    for session, count in session_counts.items():
        for index in range(count):
            reference = float(1 + spacing_samples * index)
            truth = 100_000.0 - 40.0 * index
            key = ForecastTargetKeyV1(
                session_id=session,
                episode_id=DIGEST,
                target_mask_digest=OTHER_DIGEST,
                frame_start_sample=int(reference),
                reference_sample=reference,
                continuity_segment_id=0,
            )
            complete = index >= incomplete_prefix
            rows.append(
                PredictionLedgerRowV1(
                    target=key,
                    forecasts=tuple(
                        _forecast(
                            method_index,
                            target_reference=reference,
                            predicted=truth
                            + (
                                quadratic_error_hz
                                if config.name == PRIMARY_ASSOCIATION_METHOD
                                else baseline_error_hz
                                if config.name == BASELINE_ASSOCIATION_METHOD
                                else 10.0
                            ),
                            complete=complete,
                        )
                        for method_index, config in enumerate(DEFAULT_STRICT_PAST_CONFIGS)
                    ),
                )
            )
    document = {
        "schema": PREDICTION_LEDGER_SCHEMA,
        "phase": "pre_response_prediction_freeze",
        "source_v2_file_sha256": DIGEST,
        "source_v2_manifest_digest": OTHER_DIGEST,
        "forecast_implementation_sha256": DIGEST,
        "forecast_configuration_digest": canonical_digest(
            [item.model_dump(mode="json") for item in DEFAULT_STRICT_PAST_CONFIGS]
        ),
        "future_odd_qin_outcomes_opened": False,
        "target_even_numeric_cfo_consumed": False,
        "target_count": len(rows),
        "rows": [item.model_dump(mode="json") for item in rows],
    }
    return DopplerHoldoutPredictionLedgerV1.model_validate(
        {**document, "ledger_digest": canonical_digest(document)}
    )


def _attachment(
    ledger: DopplerHoldoutPredictionLedgerV1,
    *,
    missing_last: bool = False,
) -> OddQinAttachmentLedgerV2:
    rows: list[OddQinAttachmentRowV2] = []
    for index, prediction in enumerate(ledger.rows):
        is_missing = missing_last and index == len(ledger.rows) - 1
        if is_missing:
            response = OddQinResponseMeasurementV2(
                prediction_ledger_digest=ledger.ledger_digest,
                target=prediction.target,
                status="missing",
                missing_reason="odd_response_unavailable",
                accuracy_disposition="missing",
            )
        else:
            truth = 100_000.0 - 40.0 * ((prediction.target.frame_start_sample - 1) // 20)
            response = OddQinResponseMeasurementV2(
                prediction_ledger_digest=ledger.ledger_digest,
                target=prediction.target,
                status="finite",
                accuracy_disposition="eligible",
                odd_absolute_cfo_hz=truth,
                odd_frequency_uncertainty_hz=20.0,
                odd_exact_coherence=0.3,
                odd_rolled_control_coherence=0.1,
                odd_coherence_margin=0.2,
                odd_phase_residual_rms_rad=0.2,
                odd_search_boundary=False,
            )
        rows.append(
            OddQinAttachmentRowV2(
                target=prediction.target,
                prediction_ledger_digest=ledger.ledger_digest,
                response=response,
            )
        )
    document = {
        "schema": ODD_ATTACHMENT_SCHEMA_V2,
        "prediction_ledger_digest": ledger.ledger_digest,
        "prediction_membership_or_values_mutated": False,
        "target_count": len(rows),
        "finite_response_count": sum(row.response.status == "finite" for row in rows),
        "accuracy_eligible_count": sum(
            row.response.accuracy_disposition == "eligible" for row in rows
        ),
        "boundary_response_count": 0,
        "no_support_response_count": 0,
        "missing_response_count": sum(row.response.status == "missing" for row in rows),
        "rows": [row.model_dump(mode="json") for row in rows],
    }
    return OddQinAttachmentLedgerV2.model_validate(
        {**document, "attachment_digest": canonical_digest(document)}
    )


def test_split_is_frozen_from_all_targets_before_prediction_filtering() -> None:
    ledger = _ledger({"capture-a": 15}, incomplete_prefix=3)
    inventory = freeze_association_bins(
        ledger,
        first_sample_utc_ns={"capture-a": 1_000_000_000},
        sample_rate_hz={"capture-a": RATE_HZ},
    )[0]

    assert len(inventory.bins) == 12
    assert sum(item.split == "training" for item in inventory.bins) == 6
    assert sum(item.split == "evaluation" for item in inventory.bins) == 6
    assert inventory.evaluable


def test_wrong_time_control_family_is_exact_and_excludes_positive_test() -> None:
    offsets = frozen_wrong_time_offsets_s()

    assert len(offsets) == 40
    assert offsets[:2] == (-18_000.0, -17_100.0)
    assert offsets[19:21] == (-900.0, 900.0)
    assert offsets[-2:] == (17_100.0, 18_000.0)
    assert 0.0 not in offsets
    assert all(
        right - left == 900.0 for left, right in zip(offsets[:20], offsets[1:20], strict=False)
    )
    assert all(
        right - left == 900.0 for left, right in zip(offsets[20:], offsets[21:], strict=False)
    )


def test_within_track_permutations_are_deterministic_and_training_local() -> None:
    ledger = _ledger({"capture-a": 15})
    inventory = freeze_association_bins(
        ledger,
        first_sample_utc_ns={"capture-a": 1_000_000_000},
        sample_rate_hz={"capture-a": RATE_HZ},
    )[0]

    first = freeze_within_track_permutation_controls(inventory)
    second = freeze_within_track_permutation_controls(inventory)

    assert first == second
    assert len(first) == WITHIN_TRACK_PERMUTATION_COUNT == 20
    assert [item.control_id for item in first] == [
        f"within-track-permutation-{index:02d}" for index in range(1, 21)
    ]
    training = [index for index, item in enumerate(inventory.bins) if item.split == "training"]
    evaluation = [index for index, item in enumerate(inventory.bins) if item.split == "evaluation"]
    original_training = [inventory.bins[index].primary_cfo_hz for index in training]
    for control in first:
        assert control.seed == WITHIN_TRACK_PERMUTATION_SEED == 20_260_826
        assert control.lane == PRIMARY_ASSOCIATION_METHOD
        assert control.inventory.prediction_ledger_digest == inventory.prediction_ledger_digest
        assert [control.inventory.bins[index].primary_cfo_hz for index in training] != (
            original_training
        )
        assert sorted(control.inventory.bins[index].primary_cfo_hz for index in training) == (
            sorted(original_training)
        )
        assert [control.inventory.bins[index] for index in evaluation] == [
            inventory.bins[index] for index in evaluation
        ]
        assert [item.baseline_cfo_hz for item in control.inventory.bins] == [
            item.baseline_cfo_hz for item in inventory.bins
        ]
        assert [item.target_frame_start_samples for item in control.inventory.bins] == [
            item.target_frame_start_samples for item in inventory.bins
        ]


def test_rolling_origins_use_full_target_span_and_retain_failed_controls() -> None:
    ledger = _ledger({"capture-a": 15}, incomplete_prefix=3)
    origin = 1_000_000_000
    inventory = freeze_association_bins(
        ledger,
        first_sample_utc_ns={"capture-a": origin},
        sample_rate_hz={"capture-a": RATE_HZ},
    )[0]
    all_target_utc = tuple(
        origin + round(row.target.reference_sample * 1_000_000_000 / RATE_HZ) for row in ledger.rows
    )

    controls = freeze_rolling_origin_controls(
        inventory,
        full_target_span_utc_ns=(min(all_target_utc), max(all_target_utc)),
    )

    assert tuple(item.training_fraction for item in controls) == (ROLLING_ORIGIN_TRAINING_FRACTIONS)
    assert tuple(item.control_id for item in controls) == (
        "rolling-origin-040",
        "rolling-origin-060",
        "rolling-origin-080",
    )
    assert tuple(item.split_cutoff_utc_ns for item in controls) == (
        1_113_000_000,
        1_169_000_000,
        1_225_000_000,
    )
    assert tuple(
        sum(item.split == "training" for item in control.inventory.bins) for control in controls
    ) == (3, 6, 9)
    assert controls[0].inventory.failure_reasons == ("insufficient_training_bins",)
    assert not controls[0].inventory.evaluable
    assert controls[1].inventory == inventory
    assert controls[2].inventory.failure_reasons == ("insufficient_evaluation_bins",)
    assert not controls[2].inventory.evaluable
    assert all(len(control.inventory.bins) == len(inventory.bins) for control in controls)


def test_control_helpers_reject_target_span_and_ranking_authority_drift() -> None:
    ledger = _ledger({"capture-a": 15})
    inventory = freeze_association_bins(
        ledger,
        first_sample_utc_ns={"capture-a": 1_000_000_000},
        sample_rate_hz={"capture-a": RATE_HZ},
    )[0]
    with pytest.raises(ValueError, match="outside the full target UTC span"):
        freeze_rolling_origin_controls(
            inventory,
            full_target_span_utc_ns=(
                inventory.bins[1].center_utc_ns,
                inventory.bins[-1].center_utc_ns,
            ),
        )

    measured = np.asarray([item.primary_cfo_hz for item in inventory.bins])
    ranking = freeze_candidate_ranking(
        inventory,
        lane=PRIMARY_ASSOCIATION_METHOD,
        candidate_ids=("STARLINK-A", "STARLINK-B"),
        candidate_prediction_hz=np.vstack([measured, measured + 100.0]),
    )
    validate_frozen_candidate_ranking(ranking, inventory)
    with pytest.raises(ValueError, match="records response access"):
        validate_frozen_candidate_ranking(replace(ranking, response_accessed=True), inventory)


def test_candidate_identity_and_nuisance_are_frozen_before_odd_scoring() -> None:
    ledger = _ledger({"capture-a": 15})
    inventory = freeze_association_bins(
        ledger,
        first_sample_utc_ns={"capture-a": 1_000_000_000},
        sample_rate_hz={"capture-a": RATE_HZ},
    )[0]
    measured = np.asarray([item.primary_cfo_hz for item in inventory.bins])
    candidate_predictions = np.vstack([measured - 1_000.0, measured + np.arange(len(measured))])
    ranking = freeze_candidate_ranking(
        inventory,
        lane=PRIMARY_ASSOCIATION_METHOD,
        candidate_ids=("STARLINK-A", "STARLINK-B"),
        candidate_prediction_hz=candidate_predictions,
    )

    assert next(item for item in ranking.fits if item.rank == 1).candidate_id == "STARLINK-A"
    responses = {
        item.bin_id: FrozenOddBinResponse(
            bin_id=item.bin_id,
            target_count=item.target_count,
            eligible_count=item.target_count,
            boundary_count=0,
            no_support_count=0,
            missing_count=0,
            median_eligible_cfo_hz=item.primary_cfo_hz - 1_000.0,
        )
        for item in inventory.bins
    }
    last = inventory.bins[-1]
    responses[last.bin_id] = FrozenOddBinResponse(
        bin_id=last.bin_id,
        target_count=last.target_count,
        eligible_count=0,
        boundary_count=0,
        no_support_count=0,
        missing_count=last.target_count,
        median_eligible_cfo_hz=None,
    )
    scored = score_frozen_candidate_ranking(
        ranking,
        inventory,
        odd_response_by_bin=responses,
    )

    assert scored.scores[0].candidate_id == "STARLINK-A"
    assert scored.scores[0].heldout_finite_bin_count == 5
    assert ranking.response_accessed is False

    mutated_fit = replace(ranking.fits[0], rate_departure_hz_s=1.0)
    mutated_ranking = replace(ranking, fits=(mutated_fit,) + ranking.fits[1:])
    with pytest.raises(ValueError, match="refit nuisance"):
        score_frozen_candidate_ranking(
            mutated_ranking,
            inventory,
            odd_response_by_bin=responses,
        )

    no_median = replace(responses[last.bin_id], eligible_count=1, missing_count=0)
    with pytest.raises(ValueError, match="eligible median"):
        score_frozen_candidate_ranking(
            ranking,
            inventory,
            odd_response_by_bin={**responses, last.bin_id: no_median},
        )


def test_shared_radio_rate_is_penalized_bounded_and_cannot_change_identity() -> None:
    ledger = _ledger({"capture-a": 15, "capture-b": 15})
    inventories = freeze_association_bins(
        ledger,
        first_sample_utc_ns={"capture-a": 1_000_000_000, "capture-b": 2_000_000_000},
        sample_rate_hz={"capture-a": RATE_HZ, "capture-b": RATE_HZ},
    )
    rankings = []
    for inventory in inventories:
        measured = np.asarray([item.primary_cfo_hz for item in inventory.bins])
        time = np.arange(len(measured), dtype=float) * 0.02
        predictions = np.vstack([measured - 500.0 - 80.0 * time, measured + 2_000.0])
        rankings.append(
            freeze_candidate_ranking(
                inventory,
                lane=PRIMARY_ASSOCIATION_METHOD,
                candidate_ids=("winner", "loser"),
                candidate_prediction_hz=predictions,
            )
        )

    sensitivity = fit_shared_radio_rate_sensitivity(
        rankings,
        inventories,
        physical_radio_by_session={"capture-a": "radio-x", "capture-b": "radio-x"},
    )

    assert sensitivity.may_change_candidate_identity is False
    assert sensitivity.physical_radio_ids == ("radio-x",)
    assert abs(sensitivity.rate_departures_hz_s[0]) <= 150.0
    assert math.isfinite(sensitivity.penalized_training_rms_hz)

    first_inventory = inventories[0]
    duplicated_bins = tuple(
        replace(
            item,
            bin_id=2 * item.bin_id + copy,
            center_utc_ns=item.center_utc_ns + copy,
            target_frame_start_samples=tuple(
                2 * target + copy for target in item.target_frame_start_samples
            ),
        )
        for item in first_inventory.bins
        for copy in (0, 1)
    )
    duplicated_inventory = replace(first_inventory, bins=duplicated_bins)
    first_ranking = rankings[0]
    duplicated_predictions = tuple(
        tuple(value for value in candidate for _copy in (0, 1))
        for candidate in first_ranking.candidate_prediction_hz
    )
    duplicated_ranking = replace(
        first_ranking,
        candidate_prediction_hz=duplicated_predictions,
        training_bin_ids=tuple(item.bin_id for item in duplicated_bins if item.split == "training"),
        evaluation_bin_ids=tuple(
            item.bin_id for item in duplicated_bins if item.split == "evaluation"
        ),
    )
    duplicate_sensitivity = fit_shared_radio_rate_sensitivity(
        (duplicated_ranking, rankings[1]),
        (duplicated_inventory, inventories[1]),
        physical_radio_by_session={"capture-a": "radio-x", "capture-b": "radio-x"},
    )

    assert duplicate_sensitivity.rate_departures_hz_s == pytest.approx(
        sensitivity.rate_departures_hz_s,
        abs=1e-5,
    )
    assert duplicate_sensitivity.penalized_training_rms_hz == pytest.approx(
        sensitivity.penalized_training_rms_hz,
        abs=1e-5,
    )


def test_forecast_scoring_uses_common_mask_and_fixed_gate() -> None:
    ledger = _ledger(
        {f"capture-{index}": 15 for index in range(10)},
        baseline_error_hz=20.0,
        quadratic_error_hz=5.0,
    )
    attachment = _attachment(ledger, missing_last=True)
    scores = score_forecasts(ledger, attachment)
    by_method = {item.method: item for item in scores}

    assert {item.common_accuracy_count for item in scores} == {149}
    assert by_method[PRIMARY_ASSOCIATION_METHOD].equal_capture_rms_hz == pytest.approx(5.0)
    assert by_method[BASELINE_ASSOCIATION_METHOD].equal_capture_rms_hz == pytest.approx(20.0)
    gate = quadratic_promotion_gate(scores)
    assert gate.passed
    assert gate.capture_wins == 10
    assert gate.ratio == pytest.approx(0.25)

    quadratic = by_method[PRIMARY_ASSOCIATION_METHOD]
    missing_capture = replace(quadratic.captures[-1], rms_hz=None, bias_hz=None)
    incomplete_quadratic = replace(
        quadratic,
        captures=quadratic.captures[:-1] + (missing_capture,),
    )
    failed = quadratic_promotion_gate(
        tuple(
            incomplete_quadratic if item.method == PRIMARY_ASSOCIATION_METHOD else item
            for item in scores
        )
    )
    assert not failed.passed
    assert "not_all_10_captures_compared" in failed.failed_conditions

    first_row = attachment.rows[0]
    changed_target = first_row.target.model_copy(
        update={"reference_sample": first_row.target.reference_sample + 0.25}
    )
    changed_response = first_row.response.model_copy(update={"target": changed_target})
    changed_row = first_row.model_copy(
        update={"target": changed_target, "response": changed_response}
    )
    changed_rows = (changed_row,) + attachment.rows[1:]
    changed_document = attachment.model_dump(mode="json", exclude={"attachment_digest", "rows"})
    changed_document["rows"] = [item.model_dump(mode="json") for item in changed_rows]
    changed_attachment = OddQinAttachmentLedgerV2.model_validate(
        {
            **changed_document,
            "attachment_digest": canonical_digest(changed_document),
        }
    )
    with pytest.raises(ValueError, match="target contracts"):
        score_forecasts(ledger, changed_attachment)


def test_odd_bin_join_uses_exact_prediction_complete_target_membership() -> None:
    from leo.analysis.research.final_doppler_holdout import (
        aggregate_odd_responses_to_frozen_bins,
    )

    ledger = _ledger({"capture-a": 15}, incomplete_prefix=1, spacing_samples=5)
    inventory = freeze_association_bins(
        ledger,
        first_sample_utc_ns={"capture-a": 1_000_000_000},
        sample_rate_hz={"capture-a": RATE_HZ},
    )[0]
    attachment = _attachment(ledger)

    aggregated = aggregate_odd_responses_to_frozen_bins(
        inventory,
        attachment,
        first_sample_utc_ns=1_000_000_000,
        sample_rate_hz=RATE_HZ,
    )

    first_bin = inventory.bins[0]
    assert first_bin.target_count == 3
    assert first_bin.target_frame_start_samples == (6, 11, 16)
    assert aggregated[first_bin.bin_id].target_count == 3
