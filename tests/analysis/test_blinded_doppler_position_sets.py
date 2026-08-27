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
from leo.analysis.blinded_doppler_position_sets import (
    solve_blinded_local_doppler_correction_set_position,
)
from leo.analysis.blinded_position_evaluation_sets import (
    evaluate_blinded_position_correction_set_reveal,
)
from leo.contracts.base import ContractModel
from leo.contracts.digests import canonical_digest
from leo.contracts.satellite_pnt import (
    BlindedPositionTruthV1,
    EarthAltitudeConstraintV1,
    LocalEcefGaussianPriorV1,
    SatelliteCorrectionModeV1,
)
from leo.contracts.satellite_pnt_challenge_v2 import (
    BlindedPositionCorrectionSetChallengeV2,
)
from leo.contracts.satellite_pnt_reveal_v2 import (
    BlindedPositionCorrectionSetRevealReceiptV2,
)
from leo.contracts.satellite_pnt_sets import SatelliteCorrectionSetV1
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
from tests.contracts.test_satellite_pnt_sets import _set


def _seal[ModelT: ContractModel](
    model: type[ModelT], values: dict[str, Any], digest_field: str = "content_digest"
) -> ModelT:
    draft = model.model_construct(**{**values, digest_field: _digest("draft-v2")})
    payload = draft.model_dump(mode="json", exclude={digest_field}, warnings=False)
    return model.model_validate({**payload, digest_field: canonical_digest(payload)})


def _challenge(
    correction_set: SatelliteCorrectionSetV1,
    *,
    truth_commitment_digest: str | None = None,
) -> BlindedPositionCorrectionSetChallengeV2:
    observation = _observation_ref(16)
    return _seal(
        BlindedPositionCorrectionSetChallengeV2,
        {
            "challenge_id": "synthetic-correction-set-position",
            "challenge_group_id": "synthetic-correction-set-group",
            "protocol_digest": _digest("correction-set-position-protocol"),
            "created_utc_ns": _TARGET_END + 1,
            "truth_commitment_digest": (
                _digest("inaccessible-correction-set-truth")
                if truth_commitment_digest is None
                else truth_commitment_digest
            ),
            "target_evidence_digest": canonical_digest((observation.model_dump(mode="json"),)),
            "source_fingerprint_authority_digest": _digest("source-authority"),
            "observations": (observation,),
            "reference_utc_ns": _REFERENCE,
            "prior": LocalEcefGaussianPriorV1(
                prior_provenance_digest=_digest("correction-set-local-prior"),
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
            "oracle_assignment_digest": _digest("correction-set-oracle-assignment"),
            "correction_set": correction_set,
        },
    )


def _selected_modes(
    correction_set: SatelliteCorrectionSetV1,
) -> tuple[SatelliteCorrectionModeV1, ...]:
    return tuple(
        next(
            mode
            for mode in member.correction_product.modes
            if mode.mode_digest == member.selected_mode_digest
        )
        for member in correction_set.members
    )


def _evidence(
    challenge: BlindedPositionCorrectionSetChallengeV2,
    *,
    receiver_frequency_bias_hz: float = 75.0,
) -> BlindedDopplerPositionEvidence:
    rows: list[FrozenDopplerPositionObservation] = []
    modes = _selected_modes(challenge.correction_set)
    for satellite_index, mode in enumerate(modes):
        for time_index, local_time_s in enumerate((2.0, 6.0, 10.0, 14.0)):
            position, velocity = _satellite_state(satellite_index, local_time_s)
            rows.append(
                FrozenDopplerPositionObservation(
                    observation_id=_digest(f"v2-observation-{satellite_index}-{time_index}"),
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
                        receiver_frequency_bias_hz=receiver_frequency_bias_hz,
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
        state_provider_digest=_digest("correction-set-state-provider"),
        hypotheses=(
            FrozenDopplerPositionHypothesis(
                correction_mode_digests=tuple(sorted(item.mode_digest for item in modes)),
                observations=ordered,
            ),
        ),
    )


def test_oracle_correction_set_recovers_position_without_probability_reinterpretation() -> None:
    correction_set = _set()
    challenge = _challenge(correction_set)

    estimate = solve_blinded_local_doppler_correction_set_position(
        challenge=challenge,
        evidence=_evidence(challenge),
        config=BlindedDopplerPositionConfig(),
        sealed_utc_ns=_TARGET_END + 2,
    )

    assert estimate.status is StandardScientificStatus.COMPLETE
    assert estimate.truth_accessed is False
    assert estimate.truth_metrics_included is False
    assert estimate.consumed_correction_set_digest == correction_set.content_digest
    assert estimate.consumed_oracle_assignment_digest == challenge.oracle_assignment_digest
    assert len(estimate.modes) == 1
    assert len(estimate.modes[0].associated_catalog_numbers) == 4
    assert len(estimate.modes[0].consumed_correction_mode_digests) == 4
    assert sum(
        member.correction_product.modes[0].posterior_probability
        for member in correction_set.members
    ) == pytest.approx(4.0)
    error_m = math.dist(estimate.modes[0].mean_ecef_m, _TRUTH_ECEF_M)
    assert error_m < 1.0
    assert estimate.modes[0].receiver_clock is not None
    assert estimate.modes[0].receiver_clock.drift_s_s == pytest.approx(75.0 / _RF_HZ)


def test_v2_challenge_rejects_target_calibration_overlap_and_bad_validity() -> None:
    correction_set = _set()
    challenge = _challenge(correction_set)
    payload = challenge.model_dump(mode="json")
    payload["observations"][0]["source_recording_fingerprint"] = (
        correction_set.members[0]
        .correction_product.calibration_source_spans[0]
        .source_recording_fingerprint
    )
    payload["observations"][0]["source_sample_start"] = 0
    payload["observations"][0]["source_sample_stop"] = 100
    payload["target_evidence_digest"] = canonical_digest(tuple(payload["observations"]))
    payload["content_digest"] = canonical_digest(
        {key: value for key, value in payload.items() if key != "content_digest"}
    )
    with pytest.raises(ValidationError, match="disjoint"):
        BlindedPositionCorrectionSetChallengeV2.model_validate(payload)

    payload = challenge.model_dump(mode="json")
    payload["observations"][0]["end_utc_ns"] = correction_set.valid_until_utc_ns + 1
    payload["target_evidence_digest"] = canonical_digest(tuple(payload["observations"]))
    payload["created_utc_ns"] = correction_set.valid_until_utc_ns + 2
    payload["content_digest"] = canonical_digest(
        {key: value for key, value in payload.items() if key != "content_digest"}
    )
    with pytest.raises(ValidationError, match="validity"):
        BlindedPositionCorrectionSetChallengeV2.model_validate(payload)


def test_solver_rejects_wrong_challenge_and_incomplete_selected_mode_inventory() -> None:
    correction_set = _set()
    challenge = _challenge(correction_set)
    evidence = _evidence(challenge)
    other_challenge = _challenge(correction_set, truth_commitment_digest=_digest("other-truth"))
    with pytest.raises(BlindedDopplerPositionInputError, match="another V2 challenge"):
        solve_blinded_local_doppler_correction_set_position(
            challenge=other_challenge,
            evidence=evidence,
            config=BlindedDopplerPositionConfig(),
            sealed_utc_ns=_TARGET_END + 2,
        )

    hypothesis = evidence.hypotheses[0]
    rows = tuple(
        item
        for item in hypothesis.observations
        if item.correction_mode_digest != hypothesis.correction_mode_digests[-1]
    )
    incomplete = BlindedDopplerPositionEvidence(
        challenge_content_digest=challenge.content_digest,
        state_provider_digest=evidence.state_provider_digest,
        hypotheses=(
            FrozenDopplerPositionHypothesis(
                correction_mode_digests=hypothesis.correction_mode_digests[:-1],
                observations=rows,
            ),
        ),
    )
    with pytest.raises(BlindedDopplerPositionInputError, match="selected correction set"):
        solve_blinded_local_doppler_correction_set_position(
            challenge=challenge,
            evidence=incomplete,
            config=BlindedDopplerPositionConfig(),
            sealed_utc_ns=_TARGET_END + 2,
        )

    poisoned_provider = BlindedDopplerPositionEvidence(
        challenge_content_digest=challenge.content_digest,
        state_provider_digest=correction_set.members[0].selected_mode_digest,
        hypotheses=evidence.hypotheses,
    )
    with pytest.raises(BlindedDopplerPositionInputError, match="not isolated"):
        solve_blinded_local_doppler_correction_set_position(
            challenge=challenge,
            evidence=poisoned_provider,
            config=BlindedDopplerPositionConfig(),
            sealed_utc_ns=_TARGET_END + 2,
        )


def test_v2_solver_module_has_no_truth_or_reveal_import_port() -> None:
    source_path = (
        Path(__file__).parents[2] / "src" / "leo" / "analysis" / "blinded_doppler_position_sets.py"
    )
    module = ast.parse(source_path.read_text())
    imported = {
        alias.name
        for node in ast.walk(module)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert not any("Truth" in item or "Reveal" in item for item in imported)


def test_v2_reveal_evaluates_only_after_truth_free_estimate_is_sealed() -> None:
    correction_set = _set()
    observation = _observation_ref(16)
    truth = _seal(
        BlindedPositionTruthV1,
        {
            "challenge_group_id": "synthetic-correction-set-group",
            "target_evidence_digest": canonical_digest((observation.model_dump(mode="json"),)),
            "reference_utc_ns": _REFERENCE,
            "position": ObserverSiteV1(
                latitude_deg=37.0,
                longitude_deg=-122.0,
                altitude_m=10.0,
                label="inaccessible-correction-set-truth",
            ),
            "truth_authority_digest": _digest("correction-set-truth-authority"),
            "commitment_nonce_hex": "0123456789abcdef" * 4,
            "sealed_utc_ns": _TARGET_END,
        },
    )
    challenge = _challenge(correction_set, truth_commitment_digest=truth.content_digest)
    estimate = solve_blinded_local_doppler_correction_set_position(
        challenge=challenge,
        evidence=_evidence(challenge),
        config=BlindedDopplerPositionConfig(),
        sealed_utc_ns=_TARGET_END + 2,
    )
    receipt = _seal(
        BlindedPositionCorrectionSetRevealReceiptV2,
        {
            "challenge": challenge,
            "estimate": estimate,
            "truth": truth,
            "revealed_utc_ns": _TARGET_END + 3,
        },
        "receipt_digest",
    )

    evaluation = evaluate_blinded_position_correction_set_reveal(receipt)

    assert evaluation.reveal_receipt_digest == receipt.receipt_digest
    assert evaluation.estimate_content_digest == estimate.content_digest
    assert evaluation.truth_content_digest == truth.content_digest
    assert evaluation.reported_mode.three_dimensional_error_m < 1.0
    assert evaluation.returned_posterior_mass == pytest.approx(1.0)
    assert evaluation.unresolved_probability == 0.0


def test_v2_reveal_revalidates_nested_estimate_before_truth_metrics() -> None:
    correction_set = _set()
    observation = _observation_ref(16)
    truth = _seal(
        BlindedPositionTruthV1,
        {
            "challenge_group_id": "synthetic-correction-set-group",
            "target_evidence_digest": canonical_digest((observation.model_dump(mode="json"),)),
            "reference_utc_ns": _REFERENCE,
            "position": ObserverSiteV1(
                latitude_deg=37.0,
                longitude_deg=-122.0,
                altitude_m=10.0,
                label="inaccessible-correction-set-truth",
            ),
            "truth_authority_digest": _digest("correction-set-truth-authority"),
            "commitment_nonce_hex": "fedcba9876543210" * 4,
            "sealed_utc_ns": _TARGET_END,
        },
    )
    challenge = _challenge(correction_set, truth_commitment_digest=truth.content_digest)
    estimate = solve_blinded_local_doppler_correction_set_position(
        challenge=challenge,
        evidence=_evidence(challenge),
        config=BlindedDopplerPositionConfig(),
        sealed_utc_ns=_TARGET_END + 2,
    )
    mode = estimate.modes[0]
    object.__setattr__(
        mode,
        "mean_ecef_m",
        (mode.mean_ecef_m[0] + 100.0, mode.mean_ecef_m[1], mode.mean_ecef_m[2]),
    )
    with pytest.raises(ValidationError, match="digest"):
        _seal(
            BlindedPositionCorrectionSetRevealReceiptV2,
            {
                "challenge": challenge,
                "estimate": estimate,
                "truth": truth,
                "revealed_utc_ns": _TARGET_END + 3,
            },
            "receipt_digest",
        )
