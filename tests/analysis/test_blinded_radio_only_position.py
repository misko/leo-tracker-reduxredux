from __future__ import annotations

import ast
import inspect

import pytest
from pydantic import ValidationError

from leo.analysis import blinded_radio_only_position as radio_solver_module
from leo.analysis.blinded_doppler_position import BlindedDopplerPositionInputError
from leo.analysis.blinded_position_evaluation import (
    BlindedPositionEvaluationError,
    evaluate_blinded_position_reveal,
)
from leo.analysis.blinded_radio_only_position import solve_blinded_radio_only_no_position
from leo.contracts.digests import canonical_digest
from leo.contracts.satellite_pnt import (
    BlindedPositionChallengeV1,
    BlindedPositionRevealReceiptV1,
    NavigationLane,
    PositionEstimateReasonCode,
    RadioOnlyNoCorrectionLaneV1,
)
from leo.contracts.standard_pipeline import StandardScientificStatus
from tests.analysis.test_blinded_doppler_position import (
    _TARGET_END,
    _challenge,
    _digest,
    _product,
    _seal,
)
from tests.analysis.test_blinded_position_evaluation import _truth


def _radio_challenge(*, truth_commitment_digest: str | None = None) -> BlindedPositionChallengeV1:
    base = _challenge(
        _product(),
        observation_count=16,
        oracle=True,
        truth_commitment_digest=truth_commitment_digest,
    )
    values = base.model_dump(mode="json", exclude={"content_digest", "lane_inputs"})
    values["lane_inputs"] = RadioOnlyNoCorrectionLaneV1(
        radio_only_model_digest=_digest("radio-only-model")
    )
    return _seal(BlindedPositionChallengeV1, values)


def test_radio_only_lane_seals_a_structural_no_position_result() -> None:
    challenge = _radio_challenge()

    estimate = solve_blinded_radio_only_no_position(
        challenge=challenge,
        sealed_utc_ns=_TARGET_END + 2,
    )

    assert estimate.lane is NavigationLane.RADIO_ONLY_NO_CORRECTION
    assert estimate.status is StandardScientificStatus.NO_RESULT
    assert estimate.reason_code is PositionEstimateReasonCode.NO_POSITION_SOLUTION
    assert estimate.modes == ()
    assert estimate.reported_mode_id is None
    assert estimate.unresolved_probability == 1.0
    assert estimate.consumed_radio_only_model_digest == _digest("radio-only-model")
    assert estimate.truth_accessed is False
    assert estimate.truth_metrics_included is False


def test_radio_only_no_result_is_bound_to_reveal_but_has_no_error_mode() -> None:
    truth = _truth(16)
    challenge = _radio_challenge(truth_commitment_digest=truth.content_digest)
    estimate = solve_blinded_radio_only_no_position(
        challenge=challenge,
        sealed_utc_ns=_TARGET_END + 2,
    )
    receipt = _seal(
        BlindedPositionRevealReceiptV1,
        {
            "challenge": challenge,
            "estimate": estimate,
            "truth": truth,
            "revealed_utc_ns": _TARGET_END + 3,
        },
        "receipt_digest",
    )

    with pytest.raises(BlindedPositionEvaluationError, match="no evaluable mode"):
        evaluate_blinded_position_reveal(receipt)


def test_radio_only_solver_rejects_catalogue_lane_and_early_seal() -> None:
    catalogue_challenge = _challenge(_product(), observation_count=16, oracle=True)
    with pytest.raises(BlindedDopplerPositionInputError, match="radio-only challenge"):
        solve_blinded_radio_only_no_position(
            challenge=catalogue_challenge,
            sealed_utc_ns=_TARGET_END + 2,
        )

    with pytest.raises(BlindedDopplerPositionInputError, match="predates target"):
        solve_blinded_radio_only_no_position(
            challenge=_radio_challenge(),
            sealed_utc_ns=_TARGET_END - 1,
        )


def test_radio_only_solver_revalidates_nested_challenge() -> None:
    challenge = _radio_challenge()
    poisoned_lane = challenge.lane_inputs.model_copy(
        update={"radio_only_model_digest": _digest("mutated-radio-model")}
    )
    poisoned = challenge.model_copy(update={"lane_inputs": poisoned_lane})

    with pytest.raises(ValidationError, match="digest"):
        solve_blinded_radio_only_no_position(
            challenge=poisoned,
            sealed_utc_ns=_TARGET_END + 2,
        )


def test_radio_only_execution_digest_binds_exact_model() -> None:
    first = _radio_challenge()
    values = first.model_dump(mode="json", exclude={"content_digest", "lane_inputs"})
    values["lane_inputs"] = RadioOnlyNoCorrectionLaneV1(
        radio_only_model_digest=_digest("second-radio-only-model")
    )
    second = _seal(BlindedPositionChallengeV1, values)

    first_estimate = solve_blinded_radio_only_no_position(
        challenge=first,
        sealed_utc_ns=_TARGET_END + 2,
    )
    second_estimate = solve_blinded_radio_only_no_position(
        challenge=second,
        sealed_utc_ns=_TARGET_END + 2,
    )

    assert first_estimate.solver_execution_digest != second_estimate.solver_execution_digest


def test_radio_only_solver_has_no_truth_or_reveal_import() -> None:
    tree = ast.parse(inspect.getsource(radio_solver_module))
    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }

    assert "BlindedPositionTruthV1" not in imported_names
    assert "BlindedPositionRevealReceiptV1" not in imported_names


def test_radio_challenge_digest_is_closed() -> None:
    challenge = _radio_challenge()
    payload = challenge.model_dump(mode="json", exclude={"content_digest"})
    payload["lane_inputs"]["radio_only_model_digest"] = _digest("poison")

    with pytest.raises(ValidationError, match="digest"):
        BlindedPositionChallengeV1.model_validate(
            {**payload, "content_digest": challenge.content_digest}
        )
    assert canonical_digest(payload) != challenge.content_digest
