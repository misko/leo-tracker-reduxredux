from __future__ import annotations

import hashlib
import inspect
import math
from dataclasses import replace
from typing import Any

import numpy as np
import pytest

from leo.analysis import blinded_doppler_position as solver_module
from leo.analysis.blinded_doppler_position import (
    BlindedDopplerPositionConfig,
    BlindedDopplerPositionEvidence,
    BlindedDopplerPositionInputError,
    FrozenDopplerPositionHypothesis,
    FrozenDopplerPositionObservation,
    solve_blinded_local_doppler_position,
)
from leo.contracts.base import ContractModel
from leo.contracts.digests import canonical_digest
from leo.contracts.satellite_pnt import (
    BlindedPositionChallengeV1,
    BoundedGeodeticPriorV1,
    CalibrationSourceSpanV1,
    CorrectionEvidenceClass,
    CorrectionExpiryReason,
    EarthAltitudeConstraintV1,
    EquivalentEpochCorrectionV1,
    LocalEcefGaussianPriorV1,
    NavigationLane,
    OracleIdentityFrozenCorrectionLaneV1,
    PositionObservationSetRefV1,
    SatelliteCorrectionModeV1,
    SatelliteCorrectionProductV1,
    SatelliteCorrectionReasonCode,
    SatelliteFrequencyScope,
    SatelliteFrequencyStateV1,
    UnknownIdentityFrozenCorrectionLaneV1,
    VerifiedTleMemberV1,
)
from leo.contracts.sky import TleSnapshotRefV1
from leo.contracts.standard_pipeline import StandardScientificStatus

_LIGHT_SPEED_M_S = 299_792_458.0
_RF_HZ = 11_325_000_000.0
_CALIBRATION_START = 1_800_000_000_000_000_000
_CALIBRATION_END = _CALIBRATION_START + 5_000_000_000
_PRODUCED = _CALIBRATION_END + 1_000_000_000
_TARGET_START = _PRODUCED + 1_000_000_000
_TARGET_END = _TARGET_START + 20_000_000_000
_REFERENCE = _TARGET_START + 10_000_000_000


def _digest(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode()).hexdigest()


def _seal[ModelT: ContractModel](
    model: type[ModelT], values: dict[str, Any], digest_field: str = "content_digest"
) -> ModelT:
    draft = model.model_construct(**{**values, digest_field: _digest("draft")})
    payload = draft.model_dump(mode="json", exclude={digest_field}, warnings=False)
    return model.model_validate({**payload, digest_field: canonical_digest(payload)})


def _geodetic_to_ecef_m(
    latitude_deg: float, longitude_deg: float, altitude_m: float
) -> tuple[float, float, float]:
    semi_major = 6_378_137.0
    flattening = 1.0 / 298.257223563
    eccentricity_squared = flattening * (2.0 - flattening)
    latitude = math.radians(latitude_deg)
    longitude = math.radians(longitude_deg)
    sin_latitude = math.sin(latitude)
    cos_latitude = math.cos(latitude)
    prime_vertical = semi_major / math.sqrt(1.0 - eccentricity_squared * sin_latitude**2)
    return (
        (prime_vertical + altitude_m) * cos_latitude * math.cos(longitude),
        (prime_vertical + altitude_m) * cos_latitude * math.sin(longitude),
        (prime_vertical * (1.0 - eccentricity_squared) + altitude_m) * sin_latitude,
    )


_TRUTH_ECEF_M = _geodetic_to_ecef_m(37.0, -122.0, 10.0)


def _mode(catalog_number: int, *, probability: float, oracle: bool) -> SatelliteCorrectionModeV1:
    frequency_bias_hz = float(catalog_number - 20_000) * 3.0
    values: dict[str, Any] = {
        "catalog_number": catalog_number,
        "posterior_probability": probability,
        "evidence_class": (
            CorrectionEvidenceClass.SYNTHETIC_ORACLE
            if oracle
            else CorrectionEvidenceClass.CALIBRATED_CANDIDATE
        ),
        "selected_element_digest": _digest(f"element-{catalog_number}"),
        "element_epoch_utc_ns": _CALIBRATION_START - 10_000_000_000,
        "element_age_s_at_reference": 12.5,
        "ephemeris": EquivalentEpochCorrectionV1(
            reference_utc_ns=_CALIBRATION_START + 2_500_000_000,
            offset_s=0.0,
            variance_s2=0.0,
            boundary_hit=False,
        ),
        "frequency": SatelliteFrequencyStateV1(
            activity_epoch_id=f"activity-{catalog_number}",
            scope=SatelliteFrequencyScope.SATELLITE,
            beam_channel_id=None,
            reference_utc_ns=_CALIBRATION_START + 2_500_000_000,
            bias_hz=frequency_bias_hz,
            drift_hz_s=0.0,
            bias_variance_hz2=0.04,
            drift_variance_hz2_s2=0.0,
            bias_drift_covariance_hz2_s=0.0,
        ),
        "valid_from_utc_ns": _PRODUCED,
        "valid_until_utc_ns": _PRODUCED + 30_000_000_000,
        "expiry_reason": CorrectionExpiryReason.FIXED_VALIDITY_HORIZON,
        "navigation_eligible": True,
    }
    return _seal(SatelliteCorrectionModeV1, values, "mode_digest")


def _product(
    catalog_numbers: tuple[int, ...] = (20_001, 20_002, 20_003, 20_004),
    *,
    oracle: bool = True,
) -> SatelliteCorrectionProductV1:
    modes = tuple(
        _mode(item, probability=1.0 / len(catalog_numbers), oracle=oracle)
        for item in catalog_numbers
    )
    calibration_span = CalibrationSourceSpanV1(
        source_fingerprint_authority_digest=_digest("source-authority"),
        source_recording_fingerprint=_digest("calibration-recording"),
        source_stream_index=0,
        source_sample_start=0,
        source_sample_stop=1_000,
        start_utc_ns=_CALIBRATION_START,
        end_utc_ns=_CALIBRATION_END,
    )
    values: dict[str, Any] = {
        "calibration_protocol_digest": _digest("calibration-protocol"),
        "calibration_evidence_digest": _digest("calibration-evidence"),
        "source_fingerprint_authority_digest": _digest("source-authority"),
        "calibration_source_spans": (calibration_span,),
        "calibration_start_utc_ns": _CALIBRATION_START,
        "calibration_end_utc_ns": _CALIBRATION_END,
        "produced_utc_ns": _PRODUCED,
        "tle_snapshot": TleSnapshotRefV1(
            provider="space-track",
            collected_utc_ns=_CALIBRATION_START - 1_000_000_000,
            digest=_digest("tle-snapshot"),
            object_count=10_972,
        ),
        "tle_membership_authority_digest": _digest("tle-membership"),
        "verified_tle_members": tuple(
            VerifiedTleMemberV1(
                catalog_number=item.catalog_number,
                selected_element_digest=item.selected_element_digest,
                element_epoch_utc_ns=item.element_epoch_utc_ns,
            )
            for item in modes
        ),
        "downlink_frequency_hz": _RF_HZ,
        "association_hypothesis_digest": _digest("frozen-association"),
        "modes": modes,
        "unassigned_probability": 0.0,
        "status": StandardScientificStatus.COMPLETE,
        "reason_code": SatelliteCorrectionReasonCode.TRANSFERABLE_MODES_AVAILABLE,
    }
    return _seal(SatelliteCorrectionProductV1, values)


def _observation_ref(count: int) -> PositionObservationSetRefV1:
    return PositionObservationSetRefV1(
        product_digest=_digest("target-observation-product"),
        source_binding_digest=_digest("target-source-binding"),
        source_fingerprint_authority_digest=_digest("source-authority"),
        source_recording_fingerprint=_digest("target-recording"),
        source_stream_index=0,
        source_sample_start=0,
        source_sample_stop=count * 100,
        start_utc_ns=_TARGET_START,
        end_utc_ns=_TARGET_END,
        observation_count=count,
    )


def _challenge(
    product: SatelliteCorrectionProductV1,
    *,
    observation_count: int,
    oracle: bool = True,
    prior: LocalEcefGaussianPriorV1 | BoundedGeodeticPriorV1 | None = None,
) -> BlindedPositionChallengeV1:
    observation = _observation_ref(observation_count)
    target_evidence_digest = canonical_digest((observation.model_dump(mode="json"),))
    lane = (
        OracleIdentityFrozenCorrectionLaneV1(
            oracle_assignment_digest=_digest("oracle-assignment"),
            correction_product=product,
        )
        if oracle
        else UnknownIdentityFrozenCorrectionLaneV1(
            candidate_likelihood_bank_digest=_digest("candidate-bank"),
            correction_product=product,
        )
    )
    prior_mean = (
        _TRUTH_ECEF_M[0] + 120.0,
        _TRUTH_ECEF_M[1] - 80.0,
        _TRUTH_ECEF_M[2] + 50.0,
    )
    selected_prior = prior or LocalEcefGaussianPriorV1(
        prior_provenance_digest=_digest("local-prior"),
        mean_ecef_m=prior_mean,
        covariance_ecef_m2=(
            (1_000_000.0, 0.0, 0.0),
            (0.0, 1_000_000.0, 0.0),
            (0.0, 0.0, 1_000_000.0),
        ),
        maximum_radius_m=10_000.0,
    )
    values: dict[str, Any] = {
        "challenge_id": "synthetic-doppler-position",
        "challenge_group_id": "synthetic-position-group",
        "protocol_digest": _digest("position-protocol"),
        "created_utc_ns": _TARGET_END + 1,
        "truth_commitment_digest": _digest("inaccessible-salted-truth"),
        "target_evidence_digest": target_evidence_digest,
        "source_fingerprint_authority_digest": _digest("source-authority"),
        "observations": (observation,),
        "reference_utc_ns": _REFERENCE,
        "prior": selected_prior,
        "earth_constraint": EarthAltitudeConstraintV1(
            minimum_altitude_m=-100.0,
            maximum_altitude_m=5_000.0,
        ),
        "lane_inputs": lane,
    }
    return _seal(BlindedPositionChallengeV1, values)


def _satellite_state(
    satellite_index: int, local_time_s: float
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    base_positions = (
        np.asarray((7_000_000.0, 0.0, 0.0)),
        np.asarray((0.0, 7_000_000.0, 0.0)),
        np.asarray((0.0, 0.0, 7_000_000.0)),
        np.asarray((-7_000_000.0, 0.0, 0.0)),
    )
    velocities = (
        np.asarray((0.0, 7_500.0, 1_000.0)),
        np.asarray((-7_000.0, 0.0, 2_000.0)),
        np.asarray((5_000.0, -5_000.0, 0.0)),
        np.asarray((0.0, -7_200.0, 1_500.0)),
    )
    position = base_positions[satellite_index] + local_time_s * velocities[satellite_index]
    return (
        (float(position[0]), float(position[1]), float(position[2])),
        (
            float(velocities[satellite_index][0]),
            float(velocities[satellite_index][1]),
            float(velocities[satellite_index][2]),
        ),
    )


def _independent_cfo(
    *,
    receiver_ecef_m: tuple[float, float, float],
    satellite_position_ecef_m: tuple[float, float, float],
    satellite_velocity_ecef_m_s: tuple[float, float, float],
    satellite_frequency_bias_hz: float,
    receiver_frequency_bias_hz: float,
) -> float:
    receiver = np.asarray(receiver_ecef_m)
    position = np.asarray(satellite_position_ecef_m)
    velocity = np.asarray(satellite_velocity_ecef_m_s)
    line_of_sight = position - receiver
    range_rate = float(velocity @ line_of_sight / np.linalg.norm(line_of_sight))
    return (
        -_RF_HZ * range_rate / _LIGHT_SPEED_M_S
        + satellite_frequency_bias_hz
        + receiver_frequency_bias_hz
    )


def _evidence_rows(
    challenge: BlindedPositionChallengeV1,
    product: SatelliteCorrectionProductV1,
    *,
    receiver_frequency_bias_hz: float = 75.0,
) -> tuple[FrozenDopplerPositionObservation, ...]:
    modes = product.modes
    rows: list[FrozenDopplerPositionObservation] = []
    for satellite_index, mode in enumerate(modes):
        for time_index, local_time_s in enumerate((2.0, 6.0, 10.0, 14.0)):
            position, velocity = _satellite_state(satellite_index, local_time_s)
            measured = _independent_cfo(
                receiver_ecef_m=_TRUTH_ECEF_M,
                satellite_position_ecef_m=position,
                satellite_velocity_ecef_m_s=velocity,
                satellite_frequency_bias_hz=mode.frequency.bias_hz,
                receiver_frequency_bias_hz=receiver_frequency_bias_hz,
            )
            rows.append(
                FrozenDopplerPositionObservation(
                    observation_id=_digest(f"observation-{satellite_index}-{time_index}"),
                    observation_product_digest=challenge.observations[0].product_digest,
                    support_utc_ns=_TARGET_START + round(local_time_s * 1e9),
                    correction_mode_digest=mode.mode_digest,
                    equivalent_epoch_offset_s=mode.ephemeris.offset_s,
                    satellite_position_ecef_m=position,
                    satellite_velocity_ecef_m_s=velocity,
                    measured_cfo_hz=measured,
                    measurement_standard_uncertainty_hz=0.5,
                    satellite_state_doppler_standard_uncertainty_hz=0.2,
                )
            )
    return tuple(
        sorted(rows, key=lambda item: (item.observation_product_digest, item.observation_id))
    )


def _oracle_evidence(
    challenge: BlindedPositionChallengeV1,
    *,
    receiver_frequency_bias_hz: float = 75.0,
) -> BlindedDopplerPositionEvidence:
    assert isinstance(challenge.lane_inputs, OracleIdentityFrozenCorrectionLaneV1)
    modes = challenge.lane_inputs.correction_product.modes
    ordered_rows = _evidence_rows(
        challenge,
        challenge.lane_inputs.correction_product,
        receiver_frequency_bias_hz=receiver_frequency_bias_hz,
    )
    return BlindedDopplerPositionEvidence(
        challenge_content_digest=challenge.content_digest,
        state_provider_digest=_digest("oracle-state-provider"),
        hypotheses=(
            FrozenDopplerPositionHypothesis(
                correction_mode_digests=tuple(sorted(item.mode_digest for item in modes)),
                observations=ordered_rows,
            ),
        ),
    )


def test_oracle_lane_recovers_position_without_truth_port() -> None:
    product = _product()
    challenge = _challenge(product, observation_count=16, oracle=True)
    evidence = _oracle_evidence(challenge)

    estimate = solve_blinded_local_doppler_position(
        challenge=challenge,
        evidence=evidence,
        config=BlindedDopplerPositionConfig(),
        sealed_utc_ns=_TARGET_END + 2,
    )

    assert estimate.status is StandardScientificStatus.COMPLETE
    assert estimate.lane is NavigationLane.ORACLE_IDENTITY_FROZEN_CORRECTION
    assert estimate.truth_accessed is False
    assert estimate.truth_metrics_included is False
    assert len(estimate.modes) == 1
    error_m = math.sqrt(
        math.fsum(
            (value - truth) ** 2
            for value, truth in zip(estimate.modes[0].mean_ecef_m, _TRUTH_ECEF_M, strict=True)
        )
    )
    assert error_m < 1.0
    assert estimate.modes[0].receiver_clock is not None
    assert estimate.modes[0].receiver_clock.drift_s_s == pytest.approx(75.0 / _RF_HZ)
    assert set(estimate.modes[0].associated_catalog_numbers) == {
        item.catalog_number for item in product.modes
    }


def test_analytic_position_jacobian_matches_finite_difference() -> None:
    product = _product((20_001,))
    mode = product.modes[0]
    position, velocity = _satellite_state(0, 7.0)
    observation = FrozenDopplerPositionObservation(
        observation_id=_digest("jacobian-row"),
        observation_product_digest=_digest("jacobian-product"),
        support_utc_ns=_TARGET_START + 7_000_000_000,
        correction_mode_digest=mode.mode_digest,
        equivalent_epoch_offset_s=0.0,
        satellite_position_ecef_m=position,
        satellite_velocity_ecef_m_s=velocity,
        measured_cfo_hz=0.0,
        measurement_standard_uncertainty_hz=1.0,
        satellite_state_doppler_standard_uncertainty_hz=0.0,
    )
    receiver = np.asarray(_TRUTH_ECEF_M, dtype=np.float64)
    _prediction, analytic = solver_module._predict_and_jacobian(
        receiver_ecef_m=receiver,
        receiver_frequency_bias_hz=25.0,
        observation=observation,
        correction=mode,
        downlink_frequency_hz=_RF_HZ,
    )
    for axis in range(3):
        step = 0.1
        plus = receiver.copy()
        minus = receiver.copy()
        plus[axis] += step
        minus[axis] -= step
        plus_value = solver_module._predict_and_jacobian(
            receiver_ecef_m=plus,
            receiver_frequency_bias_hz=25.0,
            observation=observation,
            correction=mode,
            downlink_frequency_hz=_RF_HZ,
        )[0]
        minus_value = solver_module._predict_and_jacobian(
            receiver_ecef_m=minus,
            receiver_frequency_bias_hz=25.0,
            observation=observation,
            correction=mode,
            downlink_frequency_hz=_RF_HZ,
        )[0]
        finite_difference = (plus_value - minus_value) / (2.0 * step)
        assert analytic[axis] == pytest.approx(finite_difference, rel=2e-6, abs=2e-7)
    assert analytic[3] == 1.0


def test_satellite_frequency_uncertainty_is_shared_across_observations() -> None:
    product = _product((20_001,))
    challenge = _challenge(product, observation_count=4, oracle=True)
    hypothesis = _oracle_evidence(challenge).hypotheses[0]
    mode = product.modes[0]

    noise = solver_module._build_observation_noise_model(
        hypothesis=hypothesis,
        correction_by_digest={mode.mode_digest: mode},
        maximum_condition=1e14,
    )
    covariance = np.linalg.inv(noise.precision)

    independent_variance = 0.5**2 + 0.2**2
    assert np.diag(covariance) == pytest.approx(
        np.full(4, independent_variance + mode.frequency.bias_variance_hz2)
    )
    assert covariance[0, 1] == pytest.approx(mode.frequency.bias_variance_hz2)
    sign, log_determinant = np.linalg.slogdet(covariance)
    assert sign > 0.0
    assert noise.log_determinant == pytest.approx(log_determinant)


def test_unknown_identity_lane_is_explicitly_partial() -> None:
    product = _product((20_001,), oracle=False)
    unknown_challenge = _challenge(product, observation_count=4, oracle=False)
    assert isinstance(unknown_challenge.lane_inputs, UnknownIdentityFrozenCorrectionLaneV1)
    rows = _evidence_rows(unknown_challenge, product)
    evidence = BlindedDopplerPositionEvidence(
        challenge_content_digest=unknown_challenge.content_digest,
        state_provider_digest=unknown_challenge.lane_inputs.candidate_likelihood_bank_digest,
        hypotheses=(
            FrozenDopplerPositionHypothesis(
                correction_mode_digests=(product.modes[0].mode_digest,),
                observations=rows,
            ),
        ),
    )

    estimate = solve_blinded_local_doppler_position(
        challenge=unknown_challenge,
        evidence=evidence,
        config=BlindedDopplerPositionConfig(),
        sealed_utc_ns=_TARGET_END + 2,
    )

    assert estimate.status is StandardScientificStatus.PARTIAL
    assert estimate.lane is NavigationLane.UNKNOWN_IDENTITY_FROZEN_CORRECTION
    assert estimate.unresolved_probability == 0.0
    assert estimate.truth_accessed is False


def test_unknown_identity_keeps_equal_catalogue_modes_ambiguous() -> None:
    product = _product((20_001, 20_002), oracle=False)
    challenge = _challenge(product, observation_count=4, oracle=False)
    assert isinstance(challenge.lane_inputs, UnknownIdentityFrozenCorrectionLaneV1)
    first, second = product.modes
    all_rows = _evidence_rows(challenge, product)
    first_rows = tuple(
        item for item in all_rows if item.correction_mode_digest == first.mode_digest
    )
    second_rows = tuple(
        replace(item, correction_mode_digest=second.mode_digest) for item in first_rows
    )
    hypotheses = tuple(
        sorted(
            (
                FrozenDopplerPositionHypothesis(
                    correction_mode_digests=(first.mode_digest,), observations=first_rows
                ),
                FrozenDopplerPositionHypothesis(
                    correction_mode_digests=(second.mode_digest,), observations=second_rows
                ),
            ),
            key=lambda item: item.correction_mode_digests,
        )
    )
    evidence = BlindedDopplerPositionEvidence(
        challenge_content_digest=challenge.content_digest,
        state_provider_digest=challenge.lane_inputs.candidate_likelihood_bank_digest,
        hypotheses=hypotheses,
    )

    estimate = solve_blinded_local_doppler_position(
        challenge=challenge,
        evidence=evidence,
        config=BlindedDopplerPositionConfig(),
        sealed_utc_ns=_TARGET_END + 2,
    )

    assert estimate.status is StandardScientificStatus.PARTIAL
    assert len(estimate.modes) == 2
    assert tuple(item.posterior_probability for item in estimate.modes) == pytest.approx((0.5, 0.5))
    assert {item.associated_catalog_numbers for item in estimate.modes} == {
        (20_001,),
        (20_002,),
    }


def test_solver_rejects_stale_evidence_tau_count_provider_and_work_poison() -> None:
    product = _product()
    challenge = _challenge(product, observation_count=16, oracle=True)
    evidence = _oracle_evidence(challenge)

    object.__setattr__(evidence, "truth_fields_excluded", False)
    with pytest.raises(BlindedDopplerPositionInputError, match="boundary flags"):
        solve_blinded_local_doppler_position(
            challenge=challenge,
            evidence=evidence,
            config=BlindedDopplerPositionConfig(),
            sealed_utc_ns=_TARGET_END + 2,
        )

    clean = _oracle_evidence(challenge)
    poisoned_row = clean.hypotheses[0].observations[0]
    object.__setattr__(poisoned_row, "equivalent_epoch_offset_s", 1.0)
    with pytest.raises(BlindedDopplerPositionInputError, match="digest is stale"):
        solve_blinded_local_doppler_position(
            challenge=challenge,
            evidence=clean,
            config=BlindedDopplerPositionConfig(),
            sealed_utc_ns=_TARGET_END + 2,
        )

    clean = _oracle_evidence(challenge)
    with pytest.raises(BlindedDopplerPositionInputError, match="work bound"):
        solve_blinded_local_doppler_position(
            challenge=challenge,
            evidence=clean,
            config=BlindedDopplerPositionConfig(maximum_observation_evaluations=10),
            sealed_utc_ns=_TARGET_END + 2,
        )

    with pytest.raises(BlindedDopplerPositionInputError, match="covariance dimension"):
        solve_blinded_local_doppler_position(
            challenge=challenge,
            evidence=clean,
            config=BlindedDopplerPositionConfig(maximum_dense_covariance_dimension=10),
            sealed_utc_ns=_TARGET_END + 2,
        )

    unknown_product = _product((20_001,), oracle=False)
    unknown = _challenge(unknown_product, observation_count=4, oracle=False)
    assert isinstance(unknown.lane_inputs, UnknownIdentityFrozenCorrectionLaneV1)
    wrong_provider = BlindedDopplerPositionEvidence(
        challenge_content_digest=unknown.content_digest,
        state_provider_digest=_digest("wrong-provider"),
        hypotheses=(
            FrozenDopplerPositionHypothesis(
                correction_mode_digests=(
                    unknown.lane_inputs.correction_product.modes[0].mode_digest,
                ),
                observations=_evidence_rows(unknown, unknown_product),
            ),
        ),
    )
    with pytest.raises(BlindedDopplerPositionInputError, match="frozen candidate bank"):
        solve_blinded_local_doppler_position(
            challenge=unknown,
            evidence=wrong_provider,
            config=BlindedDopplerPositionConfig(),
            sealed_utc_ns=_TARGET_END + 2,
        )


def test_broad_prior_is_rejected_before_numerical_work() -> None:
    product = _product()
    broad_prior = BoundedGeodeticPriorV1(
        prior_provenance_digest=_digest("broad-prior"),
        latitude_lower_deg=30.0,
        latitude_upper_deg=45.0,
        longitude_lower_deg=-130.0,
        longitude_upper_deg=-115.0,
        altitude_lower_m=-100.0,
        altitude_upper_m=5_000.0,
    )
    challenge = _challenge(
        product,
        observation_count=16,
        oracle=True,
        prior=broad_prior,
    )
    evidence = _oracle_evidence(challenge)
    with pytest.raises(BlindedDopplerPositionInputError, match="local ECEF"):
        solve_blinded_local_doppler_position(
            challenge=challenge,
            evidence=evidence,
            config=BlindedDopplerPositionConfig(),
            sealed_utc_ns=_TARGET_END + 2,
        )


def test_solver_module_has_no_truth_or_reveal_import_port() -> None:
    source = inspect.getsource(solver_module)
    assert "BlindedPositionTruthV1" not in source
    assert "BlindedPositionRevealReceiptV1" not in source
    assert "ObserverSiteV1" not in source
    signature = inspect.signature(solve_blinded_local_doppler_position)
    assert "truth" not in signature.parameters
