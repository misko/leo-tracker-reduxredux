from __future__ import annotations

import ast
import math
from pathlib import Path
from typing import Any

import pytest

from leo.analysis.blinded_doppler_position import (
    BlindedDopplerPositionConfig,
    BlindedDopplerPositionEvidence,
    BlindedDopplerPositionInputError,
    FrozenDopplerPositionHypothesis,
    FrozenDopplerPositionObservation,
)
from leo.analysis.blinded_doppler_position_joint import (
    solve_blinded_local_doppler_joint_correction_position,
)
from leo.analysis.blinded_position_evaluation_joint import (
    evaluate_blinded_position_joint_correction_reveal,
)
from leo.analysis.satellite_correction_hypotheses import (
    build_joint_correction_hypothesis_set,
)
from leo.contracts.base import ContractModel
from leo.contracts.digests import canonical_digest
from leo.contracts.satellite_pnt import (
    BlindedPositionTruthV1,
    EarthAltitudeConstraintV1,
    LocalEcefGaussianPriorV1,
    SatelliteCorrectionModeV1,
)
from leo.contracts.satellite_pnt_hypotheses import (
    JointCorrectionHypothesisV1,
    SatelliteCorrectionHypothesisSetV1,
)
from leo.contracts.satellite_pnt_joint_challenge import (
    BlindedPositionJointCorrectionChallengeV3,
)
from leo.contracts.satellite_pnt_joint_reveal import (
    BlindedPositionJointCorrectionRevealReceiptV3,
)
from leo.contracts.sky import ObserverSiteV1
from leo.contracts.standard_pipeline import StandardScientificStatus
from tests.analysis.test_blinded_doppler_position import (
    _REFERENCE,
    _RF_HZ,
    _TARGET_END,
    _TARGET_START,
    _TRUTH_ECEF_M,
    _digest,
    _independent_cfo,
    _observation_ref,
    _satellite_state,
)
from tests.analysis.test_satellite_correction_hypotheses import _reweighted_product


def _seal[ModelT: ContractModel](
    model: type[ModelT], values: dict[str, Any], digest_field: str = "content_digest"
) -> ModelT:
    draft = model.model_construct(**{**values, digest_field: _digest("joint-position-draft")})
    payload = draft.model_dump(mode="json", exclude={digest_field}, warnings=False)
    return model.model_validate({**payload, digest_field: canonical_digest(payload)})


def _family() -> SatelliteCorrectionHypothesisSetV1:
    products = tuple(
        (
            f"slot-{index:02d}",
            _reweighted_product(
                (50_001 + index,),
                (0.9,),
                unassigned_probability=0.1,
                lineage=f"position-slot-{index}",
            ),
        )
        for index in range(4)
    )
    return build_joint_correction_hypothesis_set(
        slot_products=products,
        jointing_protocol_digest=_digest("joint-position-family-protocol"),
    )


def _ambiguous_family() -> SatelliteCorrectionHypothesisSetV1:
    products = [
        (
            "slot-00",
            _reweighted_product(
                (50_001, 50_005),
                (0.45, 0.45),
                unassigned_probability=0.1,
                lineage="ambiguous-position-slot-0",
            ),
        )
    ]
    products.extend(
        (
            f"slot-{index:02d}",
            _reweighted_product(
                (50_001 + index,),
                (0.9,),
                unassigned_probability=0.1,
                lineage=f"ambiguous-position-slot-{index}",
            ),
        )
        for index in range(1, 4)
    )
    return build_joint_correction_hypothesis_set(
        slot_products=tuple(products),
        jointing_protocol_digest=_digest("ambiguous-joint-position-family"),
    )


def _challenge(
    family: SatelliteCorrectionHypothesisSetV1,
    *,
    truth_commitment_digest: str | None = None,
) -> BlindedPositionJointCorrectionChallengeV3:
    observation = _observation_ref(16)
    return _seal(
        BlindedPositionJointCorrectionChallengeV3,
        {
            "challenge_id": "synthetic-joint-correction-position",
            "challenge_group_id": "synthetic-joint-correction-group",
            "protocol_digest": _digest("joint-position-protocol"),
            "created_utc_ns": _TARGET_END + 1,
            "truth_commitment_digest": (
                _digest("inaccessible-joint-position-truth")
                if truth_commitment_digest is None
                else truth_commitment_digest
            ),
            "target_evidence_digest": canonical_digest((observation.model_dump(mode="json"),)),
            "source_fingerprint_authority_digest": _digest("source-authority"),
            "observations": (observation,),
            "reference_utc_ns": _REFERENCE,
            "prior": LocalEcefGaussianPriorV1(
                prior_provenance_digest=_digest("joint-position-prior"),
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
            "candidate_state_bank_digest": _digest("joint-candidate-state-bank"),
            "correction_hypothesis_set": family,
        },
    )


def _fully_assigned(family: SatelliteCorrectionHypothesisSetV1) -> JointCorrectionHypothesisV1:
    return next(
        item
        for item in family.hypotheses
        if len(item.active_catalog_numbers) == len(family.source_slots)
    )


def _modes_for_hypothesis(
    family: SatelliteCorrectionHypothesisSetV1,
    hypothesis: JointCorrectionHypothesisV1,
) -> tuple[SatelliteCorrectionModeV1, ...]:
    by_slot = {item.slot_id: item.correction_product for item in family.source_slots}
    modes = []
    for assignment in hypothesis.assignments:
        assert assignment.selected_mode_digest is not None
        product = by_slot[assignment.slot_id]
        modes.append(
            next(
                item
                for item in product.modes
                if item.mode_digest == assignment.selected_mode_digest
            )
        )
    return tuple(modes)


def _evidence(
    challenge: BlindedPositionJointCorrectionChallengeV3,
) -> BlindedDopplerPositionEvidence:
    family = challenge.correction_hypothesis_set
    hypothesis = _fully_assigned(family)
    modes = _modes_for_hypothesis(family, hypothesis)
    rows: list[FrozenDopplerPositionObservation] = []
    for satellite_index, mode in enumerate(modes):
        for time_index, local_time_s in enumerate((2.0, 6.0, 10.0, 14.0)):
            position, velocity = _satellite_state(satellite_index, local_time_s)
            rows.append(
                FrozenDopplerPositionObservation(
                    observation_id=_digest(
                        f"joint-position-observation-{satellite_index}-{time_index}"
                    ),
                    observation_product_digest=challenge.observations[0].product_digest,
                    support_utc_ns=_TARGET_START + round(local_time_s * 1e9),
                    correction_mode_digest=mode.mode_digest,
                    equivalent_epoch_offset_s=mode.ephemeris.offset_s,
                    satellite_position_ecef_m=position,
                    satellite_velocity_ecef_m_s=velocity,
                    measured_cfo_hz=_independent_cfo(
                        receiver_ecef_m=_TRUTH_ECEF_M,
                        satellite_position_ecef_m=position,
                        satellite_velocity_ecef_m_s=velocity,
                        satellite_frequency_bias_hz=mode.frequency.bias_hz,
                        receiver_frequency_bias_hz=75.0,
                    ),
                    measurement_standard_uncertainty_hz=0.5,
                    satellite_state_doppler_standard_uncertainty_hz=0.2,
                )
            )
    ordered = tuple(
        sorted(rows, key=lambda item: (item.observation_product_digest, item.observation_id))
    )
    return BlindedDopplerPositionEvidence(
        challenge_content_digest=challenge.content_digest,
        state_provider_digest=challenge.candidate_state_bank_digest,
        hypotheses=(
            FrozenDopplerPositionHypothesis(
                correction_mode_digests=tuple(sorted(item.mode_digest for item in modes)),
                observations=ordered,
            ),
        ),
    )


def _ambiguous_evidence(
    challenge: BlindedPositionJointCorrectionChallengeV3,
) -> BlindedDopplerPositionEvidence:
    family = challenge.correction_hypothesis_set
    fully_assigned = tuple(
        item
        for item in family.hypotheses
        if len(item.active_catalog_numbers) == len(family.source_slots)
    )
    hypotheses: list[FrozenDopplerPositionHypothesis] = []
    for association in fully_assigned:
        modes = _modes_for_hypothesis(family, association)
        rows: list[FrozenDopplerPositionObservation] = []
        for satellite_index, mode in enumerate(modes):
            expected_catalog = 50_001 + satellite_index
            for time_index, local_time_s in enumerate((2.0, 6.0, 10.0, 14.0)):
                true_position, true_velocity = _satellite_state(satellite_index, local_time_s)
                if mode.catalog_number == expected_catalog:
                    candidate_position, candidate_velocity = true_position, true_velocity
                else:
                    candidate_position, candidate_velocity = true_position, true_velocity
                rows.append(
                    FrozenDopplerPositionObservation(
                        observation_id=_digest(
                            f"ambiguous-joint-observation-{satellite_index}-{time_index}"
                        ),
                        observation_product_digest=challenge.observations[0].product_digest,
                        support_utc_ns=_TARGET_START + round(local_time_s * 1e9),
                        correction_mode_digest=mode.mode_digest,
                        equivalent_epoch_offset_s=mode.ephemeris.offset_s,
                        satellite_position_ecef_m=candidate_position,
                        satellite_velocity_ecef_m_s=candidate_velocity,
                        measured_cfo_hz=_independent_cfo(
                            receiver_ecef_m=_TRUTH_ECEF_M,
                            satellite_position_ecef_m=true_position,
                            satellite_velocity_ecef_m_s=true_velocity,
                            satellite_frequency_bias_hz=(
                                next(
                                    item
                                    for item in family.source_slots[
                                        satellite_index
                                    ].correction_product.modes
                                    if item.catalog_number == expected_catalog
                                ).frequency.bias_hz
                            ),
                            receiver_frequency_bias_hz=75.0,
                        ),
                        measurement_standard_uncertainty_hz=0.5,
                        satellite_state_doppler_standard_uncertainty_hz=0.2,
                    )
                )
        ordered = tuple(
            sorted(
                rows,
                key=lambda item: (item.observation_product_digest, item.observation_id),
            )
        )
        hypotheses.append(
            FrozenDopplerPositionHypothesis(
                correction_mode_digests=tuple(sorted(item.mode_digest for item in modes)),
                observations=ordered,
            )
        )
    return BlindedDopplerPositionEvidence(
        challenge_content_digest=challenge.content_digest,
        state_provider_digest=challenge.candidate_state_bank_digest,
        hypotheses=tuple(sorted(hypotheses, key=lambda item: item.correction_mode_digests)),
    )


def test_joint_position_preserves_unevaluable_prior_mass_and_recovers_position() -> None:
    family = _family()
    challenge = _challenge(family)

    estimate = solve_blinded_local_doppler_joint_correction_position(
        challenge=challenge,
        evidence=_evidence(challenge),
        config=BlindedDopplerPositionConfig(),
        sealed_utc_ns=_TARGET_END + 2,
    )

    expected_conditioning_mass = 0.9**4
    assert estimate.status is StandardScientificStatus.PARTIAL
    assert estimate.source_hypothesis_count == 16
    assert estimate.evaluated_hypothesis_count == 1
    assert estimate.unevaluable_hypothesis_count == 15
    assert estimate.conditioning_event_prior_probability == pytest.approx(
        expected_conditioning_mass
    )
    assert estimate.modes[0].posterior_probability == pytest.approx(expected_conditioning_mass)
    assert estimate.unresolved_probability == pytest.approx(1.0 - expected_conditioning_mass)
    assert estimate.target_likelihood_compared_to_unresolved is False
    assert estimate.identity_claimed is False
    assert math.dist(estimate.modes[0].mean_ecef_m, _TRUTH_ECEF_M) < 1.0
    assert estimate.modes[0].receiver_clock is not None
    assert estimate.modes[0].receiver_clock.drift_s_s == pytest.approx(75.0 / _RF_HZ)


def test_joint_position_reweights_multiple_fully_assigned_identity_modes() -> None:
    family = _ambiguous_family()
    challenge = _challenge(family)

    estimate = solve_blinded_local_doppler_joint_correction_position(
        challenge=challenge,
        evidence=_ambiguous_evidence(challenge),
        config=BlindedDopplerPositionConfig(),
        sealed_utc_ns=_TARGET_END + 2,
    )

    assert estimate.source_hypothesis_count == 24
    assert estimate.evaluated_hypothesis_count == 2
    assert estimate.conditioning_event_prior_probability == pytest.approx(0.9**4)
    assert len(estimate.modes) == 2
    assert math.fsum(item.posterior_probability for item in estimate.modes) == pytest.approx(0.9**4)
    assert estimate.modes[0].associated_catalog_numbers == (
        50_001,
        50_002,
        50_003,
        50_004,
    )
    assert estimate.modes[0].posterior_probability > estimate.modes[1].posterior_probability
    assert math.dist(estimate.modes[0].mean_ecef_m, _TRUTH_ECEF_M) < 1.0


def test_joint_solver_requires_exact_state_bank_and_evaluable_family_inventory() -> None:
    family = _family()
    challenge = _challenge(family)
    evidence = _evidence(challenge)
    wrong_bank = BlindedDopplerPositionEvidence(
        challenge_content_digest=challenge.content_digest,
        state_provider_digest=_digest("wrong-state-bank"),
        hypotheses=evidence.hypotheses,
    )
    with pytest.raises(BlindedDopplerPositionInputError, match="state bank"):
        solve_blinded_local_doppler_joint_correction_position(
            challenge=challenge,
            evidence=wrong_bank,
            config=BlindedDopplerPositionConfig(),
            sealed_utc_ns=_TARGET_END + 2,
        )

    empty_slot_family = build_joint_correction_hypothesis_set(
        slot_products=tuple(
            (item.slot_id, item.correction_product) for item in family.source_slots[:3]
        ),
        jointing_protocol_digest=_digest("only-three-slots"),
    )
    three_slot_challenge = _challenge(empty_slot_family)
    with pytest.raises(BlindedDopplerPositionInputError, match="no fully assigned"):
        solve_blinded_local_doppler_joint_correction_position(
            challenge=three_slot_challenge,
            evidence=_evidence(three_slot_challenge),
            config=BlindedDopplerPositionConfig(),
            sealed_utc_ns=_TARGET_END + 2,
        )


def test_joint_solver_module_has_no_truth_or_reveal_import_port() -> None:
    source = (
        Path(__file__).parents[2] / "src" / "leo" / "analysis" / "blinded_doppler_position_joint.py"
    )
    module = ast.parse(source.read_text())
    imported = {
        alias.name
        for node in ast.walk(module)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert not any("Truth" in item or "Reveal" in item for item in imported)


def test_joint_reveal_preserves_unresolved_mass_after_truth_is_opened() -> None:
    family = _family()
    observation = _observation_ref(16)
    truth = _seal(
        BlindedPositionTruthV1,
        {
            "challenge_group_id": "synthetic-joint-correction-group",
            "target_evidence_digest": canonical_digest((observation.model_dump(mode="json"),)),
            "reference_utc_ns": _REFERENCE,
            "position": ObserverSiteV1(
                latitude_deg=37.0,
                longitude_deg=-122.0,
                altitude_m=10.0,
                label="inaccessible-joint-position-truth",
            ),
            "truth_authority_digest": _digest("joint-position-truth-authority"),
            "commitment_nonce_hex": "0123456789abcdef" * 4,
            "sealed_utc_ns": _TARGET_END,
        },
    )
    challenge = _challenge(family, truth_commitment_digest=truth.content_digest)
    estimate = solve_blinded_local_doppler_joint_correction_position(
        challenge=challenge,
        evidence=_evidence(challenge),
        config=BlindedDopplerPositionConfig(),
        sealed_utc_ns=_TARGET_END + 2,
    )
    receipt = _seal(
        BlindedPositionJointCorrectionRevealReceiptV3,
        {
            "challenge": challenge,
            "estimate": estimate,
            "truth": truth,
            "revealed_utc_ns": _TARGET_END + 3,
        },
        "receipt_digest",
    )

    evaluation = evaluate_blinded_position_joint_correction_reveal(receipt)

    assert evaluation.reported_mode.three_dimensional_error_m < 1.0
    assert evaluation.returned_posterior_mass == pytest.approx(0.9**4)
    assert evaluation.unresolved_probability == pytest.approx(1.0 - 0.9**4)
    assert evaluation.target_likelihood_compared_to_unresolved is False
    assert evaluation.returned_posterior_mass + evaluation.unresolved_probability == pytest.approx(
        1.0
    )
