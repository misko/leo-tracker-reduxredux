from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError

from leo.analysis import blinded_position_evaluation as evaluation_module
from leo.analysis.blinded_doppler_position import (
    BlindedDopplerPositionConfig,
    solve_blinded_local_doppler_position,
)
from leo.analysis.blinded_position_evaluation import evaluate_blinded_position_reveal
from leo.contracts.digests import canonical_digest
from leo.contracts.satellite_pnt import (
    BlindedPositionRevealReceiptV1,
    BlindedPositionTruthV1,
    NavigationLane,
)
from leo.contracts.sky import ObserverSiteV1
from tests.analysis.test_blinded_doppler_position import (
    _REFERENCE,
    _TARGET_END,
    _TRUTH_ECEF_M,
    _challenge,
    _digest,
    _observation_ref,
    _oracle_evidence,
    _product,
    _seal,
)


def _truth(observation_count: int) -> BlindedPositionTruthV1:
    target_evidence_digest = canonical_digest(
        (_observation_ref(observation_count).model_dump(mode="json"),)
    )
    return _seal(
        BlindedPositionTruthV1,
        {
            "challenge_group_id": "synthetic-position-group",
            "target_evidence_digest": target_evidence_digest,
            "reference_utc_ns": _REFERENCE,
            "position": ObserverSiteV1(
                latitude_deg=37.0,
                longitude_deg=-122.0,
                altitude_m=10.0,
                label="inaccessible-synthetic-truth",
            ),
            "truth_authority_digest": _digest("truth-authority"),
            "commitment_nonce_hex": "0123456789abcdef" * 4,
            "sealed_utc_ns": _TARGET_END,
        },
    )


def _reveal_receipt() -> BlindedPositionRevealReceiptV1:
    truth = _truth(16)
    product = _product()
    challenge = _challenge(
        product,
        observation_count=16,
        oracle=True,
        truth_commitment_digest=truth.content_digest,
    )
    estimate = solve_blinded_local_doppler_position(
        challenge=challenge,
        evidence=_oracle_evidence(challenge),
        config=BlindedDopplerPositionConfig(),
        sealed_utc_ns=_TARGET_END + 2,
    )
    return _seal(
        BlindedPositionRevealReceiptV1,
        {
            "challenge": challenge,
            "estimate": estimate,
            "truth": truth,
            "revealed_utc_ns": _TARGET_END + 3,
        },
        "receipt_digest",
    )


def test_reveal_evaluator_recomputes_truth_error_after_estimate_seal() -> None:
    receipt = _reveal_receipt()

    evaluation = evaluate_blinded_position_reveal(receipt)

    assert evaluation.lane is NavigationLane.ORACLE_IDENTITY_FROZEN_CORRECTION
    assert evaluation.reveal_receipt_digest == receipt.receipt_digest
    assert evaluation.estimate_content_digest == receipt.estimate.content_digest
    assert evaluation.truth_content_digest == receipt.truth.content_digest
    assert evaluation.reported_mode.mode_id == receipt.estimate.reported_mode_id
    direct_error = np.linalg.norm(
        np.asarray(receipt.estimate.modes[0].mean_ecef_m) - np.asarray(_TRUTH_ECEF_M)
    )
    assert evaluation.reported_mode.three_dimensional_error_m == pytest.approx(direct_error)
    assert evaluation.reported_mode.horizontal_error_m >= 0.0
    assert evaluation.returned_posterior_mass == pytest.approx(1.0)
    assert evaluation.unresolved_probability == 0.0
    assert evaluation.conditional_mean_three_dimensional_error_m == pytest.approx(direct_error)
    assert evaluation.conditional_rms_three_dimensional_error_m == pytest.approx(direct_error)


def test_reveal_evaluator_revalidates_nested_estimate_before_truth_metrics() -> None:
    receipt = _reveal_receipt()
    mode = receipt.estimate.modes[0]
    object.__setattr__(
        mode,
        "mean_ecef_m",
        (mode.mean_ecef_m[0] + 1_000.0, mode.mean_ecef_m[1], mode.mean_ecef_m[2]),
    )

    with pytest.raises(ValidationError, match="digest"):
        evaluate_blinded_position_reveal(receipt)


def test_semidefinite_covariance_diagnostic_does_not_invent_precision() -> None:
    covariance = np.diag((4.0, 0.0, 0.0))

    assert evaluation_module._semidefinite_quadratic(
        np.asarray((2.0, 0.0, 0.0)), covariance
    ) == pytest.approx(1.0)
    assert (
        evaluation_module._semidefinite_quadratic(np.asarray((2.0, 1.0, 0.0)), covariance) is None
    )
    assert evaluation_module._semidefinite_quadratic(
        np.asarray((1e-10,)), np.asarray(((1e-20,),))
    ) == pytest.approx(1.0)
