"""Truth-isolated radio-only negative control for blinded navigation.

The radio-only model contains no orbit, direction, range, or range-rate map
from the measured receiver-relative CFO to geographic position.  It therefore
cannot update a position prior.  This analyzer validates and seals that
structural no-result; it does not manufacture a prior-shaped position mode or
pretend that a response-independent result is an equal-row likelihood test.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from leo.analysis.blinded_doppler_position import BlindedDopplerPositionInputError
from leo.contracts.digests import canonical_digest
from leo.contracts.satellite_pnt import (
    BlindedPositionChallengeV1,
    BlindedPositionEstimateV1,
    NavigationLane,
    PositionEstimateReasonCode,
    RadioOnlyNoCorrectionLaneV1,
)
from leo.contracts.standard_pipeline import StandardScientificStatus

_ALGORITHM_VERSION: Literal["structural-radio-only-no-position-v1"] = (
    "structural-radio-only-no-position-v1"
)


def solve_blinded_radio_only_no_position(
    *,
    challenge: BlindedPositionChallengeV1,
    sealed_utc_ns: int,
) -> BlindedPositionEstimateV1:
    """Seal the fact that a radio-only model supplies no position observable."""

    challenge = BlindedPositionChallengeV1.model_validate(challenge.model_dump(mode="json"))
    lane = challenge.lane_inputs
    if not isinstance(lane, RadioOnlyNoCorrectionLaneV1):
        raise BlindedDopplerPositionInputError(
            "structural radio-only solver requires the radio-only challenge lane"
        )
    target_end = max(item.end_utc_ns for item in challenge.observations)
    if (
        isinstance(sealed_utc_ns, bool)
        or not isinstance(sealed_utc_ns, int)
        or sealed_utc_ns < max(challenge.created_utc_ns, target_end)
    ):
        raise BlindedDopplerPositionInputError(
            "radio-only estimate seal predates target completion"
        )
    execution_digest = canonical_digest(
        {
            "algorithm_version": _ALGORITHM_VERSION,
            "challenge_content_digest": challenge.content_digest,
            "radio_only_model_digest": lane.radio_only_model_digest,
            "sealed_utc_ns": sealed_utc_ns,
            "result": "structurally-unobservable-position",
        }
    )
    config_digest = canonical_digest(
        {
            "algorithm_version": _ALGORITHM_VERSION,
            "position_observable": "absent-without-orbit-or-direction-model",
        }
    )
    values: dict[str, object] = {
        "challenge_id": challenge.challenge_id,
        "challenge_group_id": challenge.challenge_group_id,
        "challenge_content_digest": challenge.content_digest,
        "truth_commitment_digest": challenge.truth_commitment_digest,
        "lane": NavigationLane.RADIO_ONLY_NO_CORRECTION,
        "reference_utc_ns": challenge.reference_utc_ns,
        "consumed_radio_only_model_digest": lane.radio_only_model_digest,
        "solver_algorithm_version": _ALGORITHM_VERSION,
        "solver_config_digest": config_digest,
        "solver_execution_digest": execution_digest,
        "sealed_utc_ns": sealed_utc_ns,
        "status": StandardScientificStatus.NO_RESULT,
        "reason_code": PositionEstimateReasonCode.NO_POSITION_SOLUTION,
        "source_mode_count": 0,
        "returned_mode_count": 0,
        "truncated_mode_count": 0,
        "modes": (),
        "reported_mode_id": None,
        "unresolved_probability": 1.0,
        "truth_accessed": False,
        "truth_metrics_included": False,
    }
    return _seal_estimate(values)


def _seal_estimate(values: Mapping[str, object]) -> BlindedPositionEstimateV1:
    draft_values: dict[str, Any] = {
        **values,
        "content_digest": canonical_digest({"draft": "radio-only-position-estimate"}),
    }
    draft = BlindedPositionEstimateV1.model_construct(**draft_values)
    payload = draft.model_dump(mode="json", exclude={"content_digest"}, warnings=False)
    return BlindedPositionEstimateV1.model_validate(
        {**payload, "content_digest": canonical_digest(payload)}
    )
