from __future__ import annotations

import ast
import math
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from leo.analysis.blinded_doppler_position import (
    BlindedDopplerPositionConfig,
    BlindedDopplerPositionEvidence,
    BlindedDopplerPositionInputError,
    FrozenDopplerPositionHypothesis,
    FrozenDopplerPositionObservation,
)
from leo.analysis.blinded_doppler_position_native_joint import (
    native_joint_position_models,
    solve_blinded_local_doppler_native_joint_position,
)
from leo.analysis.blinded_position_evaluation_native_joint import (
    evaluate_blinded_position_native_joint_reveal,
)
from leo.contracts.base import ContractModel
from leo.contracts.digests import canonical_digest
from leo.contracts.satellite_pnt import (
    BlindedPositionTruthV1,
    EarthAltitudeConstraintV1,
    LocalEcefGaussianPriorV1,
    PositionObservationSetRefV1,
)
from leo.contracts.satellite_pnt_joint_calibration import (
    JointSatelliteCorrectionModeV1,
    JointSatelliteCorrectionProductV1,
)
from leo.contracts.satellite_pnt_native_joint_challenge import (
    BlindedPositionNativeJointCorrectionChallengeV4,
)
from leo.contracts.satellite_pnt_native_joint_reveal import (
    BlindedPositionNativeJointCorrectionRevealReceiptV4,
)
from leo.contracts.sky import ObserverSiteV1
from leo.contracts.standard_pipeline import StandardScientificStatus
from tests.analysis.test_blinded_doppler_position import (
    _CALIBRATION_START,
    _REFERENCE,
    _TARGET_END,
    _TARGET_START,
    _TRUTH_ECEF_M,
    _digest,
    _independent_cfo,
    _satellite_state,
)
from tests.analysis.test_satellite_correction_replay import (
    _CATALOG_ONE,
    _CATALOG_TWO,
    _bank,
    _graph,
    _joint_receipt,
)


def _seal[ModelT: ContractModel](
    model: type[ModelT],
    values: dict[str, Any],
    digest_field: str = "content_digest",
) -> ModelT:
    draft = model.model_construct(**{**values, digest_field: _digest("native-joint-draft")})
    payload = draft.model_dump(mode="json", exclude={digest_field}, warnings=False)
    return model.model_validate({**payload, digest_field: canonical_digest(payload)})


def _product() -> JointSatelliteCorrectionProductV1:
    graph = _graph(
        start_utc_ns=_CALIBRATION_START - 10_000_000_000,
        labels=(_CATALOG_ONE, _CATALOG_TWO),
    )
    bank = _bank(graph, candidate_numbers=(_CATALOG_ONE, _CATALOG_TWO))
    product = _joint_receipt(graph, bank).joint_correction_product
    selected_k2 = next(item for item in product.modes if len(item.active_catalog_numbers) == 2)
    selected_null = next(item for item in product.modes if not item.active_catalog_numbers)
    modes = []
    for mode in product.modes:
        probability = (
            0.8
            if mode.mode_digest == selected_k2.mode_digest
            else 0.2
            if mode.mode_digest == selected_null.mode_digest
            else 0.0
        )
        payload = mode.model_dump(mode="json", exclude={"mode_digest"})
        if mode.mode_digest == selected_k2.mode_digest:
            satellite_states = []
            for state in mode.satellite_states:
                state_payload = state.model_dump(mode="json")
                state_payload["frequency"].update(
                    {
                        "bias_variance_hz2": 1e-4,
                        "drift_variance_hz2_s2": 1e-8,
                        "bias_drift_covariance_hz2_s": 0.0,
                    }
                )
                satellite_states.append(state_payload)
            payload["satellite_states"] = tuple(satellite_states)
            payload["frequency_covariance"] = (
                (1e-4, 0.0, 2e-5, 0.0),
                (0.0, 1e-8, 0.0, 2e-9),
                (2e-5, 0.0, 1e-4, 0.0),
                (0.0, 2e-9, 0.0, 1e-8),
            )
        payload["posterior_probability"] = probability
        modes.append(
            JointSatelliteCorrectionModeV1.model_validate(
                {**payload, "mode_digest": canonical_digest(payload)}
            )
        )
    product_payload = product.model_dump(mode="json", exclude={"content_digest"})
    product_payload["modes"] = tuple(item.model_dump(mode="json") for item in modes)
    return JointSatelliteCorrectionProductV1.model_validate(
        {**product_payload, "content_digest": canonical_digest(product_payload)}
    )


def _observation_ref(
    product: JointSatelliteCorrectionProductV1,
    *,
    observation_count: int,
) -> PositionObservationSetRefV1:
    return PositionObservationSetRefV1(
        product_digest=_digest("native-joint-target-product"),
        source_binding_digest=_digest("native-joint-target-binding"),
        source_fingerprint_authority_digest=(product.source_fingerprint_authority_digest),
        source_recording_fingerprint=_digest("native-joint-target-recording"),
        source_stream_index=0,
        source_sample_start=10_000,
        source_sample_stop=20_000,
        start_utc_ns=_TARGET_START,
        end_utc_ns=_TARGET_END,
        observation_count=observation_count,
    )


def _challenge(
    product: JointSatelliteCorrectionProductV1,
    *,
    observation_count: int = 8,
    truth_commitment_digest: str | None = None,
) -> BlindedPositionNativeJointCorrectionChallengeV4:
    observation = _observation_ref(product, observation_count=observation_count)
    return _seal(
        BlindedPositionNativeJointCorrectionChallengeV4,
        {
            "challenge_id": "synthetic-native-joint-position",
            "challenge_group_id": "synthetic-native-joint-group",
            "protocol_digest": _digest("native-joint-position-protocol"),
            "created_utc_ns": _TARGET_END + 1,
            "truth_commitment_digest": (
                _digest("native-joint-inaccessible-truth")
                if truth_commitment_digest is None
                else truth_commitment_digest
            ),
            "target_evidence_digest": canonical_digest((observation.model_dump(mode="json"),)),
            "source_fingerprint_authority_digest": (product.source_fingerprint_authority_digest),
            "observations": (observation,),
            "reference_utc_ns": _REFERENCE,
            "prior": LocalEcefGaussianPriorV1(
                prior_provenance_digest=_digest("native-joint-position-prior"),
                mean_ecef_m=(
                    _TRUTH_ECEF_M[0] + 120.0,
                    _TRUTH_ECEF_M[1] - 80.0,
                    _TRUTH_ECEF_M[2] + 50.0,
                ),
                covariance_ecef_m2=(
                    (1_000_000.0, 0.0, 0.0),
                    (0.0, 1_000_000.0, 0.0),
                    (0.0, 0.0, 1_000_000.0),
                ),
                maximum_radius_m=10_000.0,
            ),
            "earth_constraint": EarthAltitudeConstraintV1(
                minimum_altitude_m=-100.0,
                maximum_altitude_m=5_000.0,
            ),
            "candidate_state_bank_digest": _digest("native-joint-state-bank"),
            "joint_correction_product": product,
        },
    )


def _evidence(
    challenge: BlindedPositionNativeJointCorrectionChallengeV4,
    *,
    rank_deficient: bool = False,
) -> BlindedDopplerPositionEvidence:
    models = native_joint_position_models(challenge.joint_correction_product)
    true_model = models[0]
    true_by_catalogue = {item.catalog_number: item for item in true_model.corrections}
    hypotheses: list[FrozenDopplerPositionHypothesis] = []
    for model in models:
        corrections_by_catalogue = {item.catalog_number: item for item in model.corrections}
        rows: list[FrozenDopplerPositionObservation] = []
        for satellite_index, catalog_number in enumerate(model.catalogue_numbers):
            correction = corrections_by_catalogue[catalog_number]
            true_correction = true_by_catalogue[catalog_number]
            for time_index, local_time_s in enumerate((2.0, 6.0, 10.0, 14.0)):
                if rank_deficient:
                    position, velocity = _satellite_state(0, 2.0)
                else:
                    position, velocity = _satellite_state(satellite_index, local_time_s)
                support_utc_ns = _TARGET_START + round(local_time_s * 1e9)
                dt_s = (support_utc_ns - true_correction.frequency.reference_utc_ns) / 1e9
                satellite_frequency_hz = (
                    true_correction.frequency.bias_hz + true_correction.frequency.drift_hz_s * dt_s
                )
                rows.append(
                    FrozenDopplerPositionObservation(
                        observation_id=_digest(
                            f"native-joint-observation-{catalog_number}-{time_index}"
                        ),
                        observation_product_digest=(challenge.observations[0].product_digest),
                        support_utc_ns=support_utc_ns,
                        correction_mode_digest=correction.mode_digest,
                        equivalent_epoch_offset_s=(correction.ephemeris.offset_s),
                        satellite_position_ecef_m=position,
                        satellite_velocity_ecef_m_s=velocity,
                        measured_cfo_hz=_independent_cfo(
                            receiver_ecef_m=_TRUTH_ECEF_M,
                            satellite_position_ecef_m=position,
                            satellite_velocity_ecef_m_s=velocity,
                            satellite_frequency_bias_hz=satellite_frequency_hz,
                            receiver_frequency_bias_hz=75.0,
                        ),
                        measurement_standard_uncertainty_hz=0.005,
                        satellite_state_doppler_standard_uncertainty_hz=0.002,
                    )
                )
        hypotheses.append(
            FrozenDopplerPositionHypothesis(
                correction_mode_digests=tuple(
                    sorted(item.mode_digest for item in model.corrections)
                ),
                observations=tuple(
                    sorted(
                        rows,
                        key=lambda item: (
                            item.observation_product_digest,
                            item.observation_id,
                        ),
                    )
                ),
            )
        )
    return BlindedDopplerPositionEvidence(
        challenge_content_digest=challenge.content_digest,
        state_provider_digest=challenge.candidate_state_bank_digest,
        hypotheses=tuple(sorted(hypotheses, key=lambda item: item.correction_mode_digests)),
    )


def test_native_joint_two_satellite_time_diversity_produces_partial_position() -> None:
    product = _product()
    challenge = _challenge(product)
    evidence = _evidence(challenge)

    estimate = solve_blinded_local_doppler_native_joint_position(
        challenge=challenge,
        evidence=evidence,
        config=BlindedDopplerPositionConfig(),
        sealed_utc_ns=_TARGET_END + 2,
    )

    assert estimate.status is StandardScientificStatus.PARTIAL
    assert estimate.minimum_data_information_rank == 4
    assert estimate.time_diverse_two_satellite_modes_permitted is True
    assert estimate.joint_frequency_covariance_consumed is True
    assert estimate.target_likelihood_compared_to_unresolved is False
    assert estimate.unresolved_probability > 0.0
    assert math.dist(estimate.modes[0].mean_ecef_m, _TRUTH_ECEF_M) < 10.0
    assert estimate.conditioning_event_prior_probability + estimate.unresolved_probability == (
        pytest.approx(1.0)
    )


def test_native_joint_rank_deficient_geometry_abstains_despite_position_prior() -> None:
    product = _product()
    challenge = _challenge(product)
    evidence = _evidence(challenge, rank_deficient=True)

    with pytest.raises(BlindedDopplerPositionInputError, match="rank-four"):
        solve_blinded_local_doppler_native_joint_position(
            challenge=challenge,
            evidence=evidence,
            config=BlindedDopplerPositionConfig(),
            sealed_utc_ns=_TARGET_END + 2,
        )


def test_native_joint_challenge_rejects_stale_nested_product() -> None:
    product = _product()
    challenge = _challenge(product)
    poisoned = product.model_copy(
        update={"association_result_digest": _digest("poisoned-association")}
    )
    stale = challenge.model_copy(update={"joint_correction_product": poisoned})

    with pytest.raises(ValidationError):
        solve_blinded_local_doppler_native_joint_position(
            challenge=stale,
            evidence=_evidence(challenge),
            config=BlindedDopplerPositionConfig(),
            sealed_utc_ns=_TARGET_END + 2,
        )


def test_native_joint_solver_has_no_truth_or_reveal_import_port() -> None:
    source = (
        Path(__file__).parents[2]
        / "src"
        / "leo"
        / "analysis"
        / "blinded_doppler_position_native_joint.py"
    )
    module = ast.parse(source.read_text())
    imported = {
        alias.name
        for node in ast.walk(module)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert not any("Truth" in item or "Reveal" in item for item in imported)


def test_native_joint_reveal_preserves_unresolved_mass() -> None:
    product = _product()
    observation = _observation_ref(product, observation_count=8)
    truth = _seal(
        BlindedPositionTruthV1,
        {
            "challenge_group_id": "synthetic-native-joint-group",
            "target_evidence_digest": canonical_digest((observation.model_dump(mode="json"),)),
            "reference_utc_ns": _REFERENCE,
            "position": ObserverSiteV1(
                latitude_deg=37.0,
                longitude_deg=-122.0,
                altitude_m=10.0,
                label="inaccessible-native-joint-truth",
            ),
            "truth_authority_digest": _digest("native-joint-truth-authority"),
            "commitment_nonce_hex": "0123456789abcdef" * 4,
            "sealed_utc_ns": _TARGET_END,
        },
    )
    challenge = _challenge(product, truth_commitment_digest=truth.content_digest)
    estimate = solve_blinded_local_doppler_native_joint_position(
        challenge=challenge,
        evidence=_evidence(challenge),
        config=BlindedDopplerPositionConfig(),
        sealed_utc_ns=_TARGET_END + 2,
    )
    receipt = _seal(
        BlindedPositionNativeJointCorrectionRevealReceiptV4,
        {
            "challenge": challenge,
            "estimate": estimate,
            "truth": truth,
            "revealed_utc_ns": _TARGET_END + 3,
        },
        "receipt_digest",
    )

    evaluation = evaluate_blinded_position_native_joint_reveal(receipt)

    assert evaluation.reported_mode.three_dimensional_error_m < 10.0
    assert evaluation.returned_posterior_mass == pytest.approx(0.8)
    assert evaluation.unresolved_probability == pytest.approx(0.2)
    assert evaluation.target_likelihood_compared_to_unresolved is False
    assert evaluation.returned_posterior_mass + evaluation.unresolved_probability == (
        pytest.approx(1.0)
    )
