from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from leo.analysis.standard.codecs import decode_standard_product
from leo.analysis.standard.products import KALMAN_TRACKING_PRODUCT
from leo.contracts.digests import canonical_digest
from leo.contracts.kalman_tracking import KalmanTrackingConfigV1, StandardKalmanTrackingV1


def _empty_document() -> dict[str, object]:
    digest = "sha256:" + "1" * 64
    config = KalmanTrackingConfigV1()
    body: dict[str, object] = {
        "schema_version": 1,
        "algorithm_version": "standard-kalman-tracking-v1",
        "path_input_binding_digest": digest,
        "pilot_scan_digest": digest,
        "dealiased_bank_digest": digest,
        "final_trajectory_bank_digest": digest,
        "config": config.model_dump(mode="json"),
        "config_digest": config.digest,
        "source_track_count": 0,
        "returned_track_count": 0,
        "truncated_track_count": 0,
        "tracks": [],
        "status": "no_result",
        "reason": "no final CFO trajectory was available for Kalman tracking",
        "candidate_only": True,
        "known_pilots_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    return {**body, "content_digest": canonical_digest(body)}


def test_kalman_product_has_a_strict_additive_standard_codec() -> None:
    document = _empty_document()

    assert StandardKalmanTrackingV1.model_validate(document).model_dump(mode="json") == document
    assert decode_standard_product(KALMAN_TRACKING_PRODUCT, document) == document


def test_kalman_product_rejects_mutation_and_frame_budget_inversion() -> None:
    document = _empty_document()
    mutated = deepcopy(document)
    mutated["known_pilots_only"] = False
    with pytest.raises(ValidationError):
        StandardKalmanTrackingV1.model_validate(mutated)

    with pytest.raises(ValidationError, match="returned Kalman frames"):
        KalmanTrackingConfigV1(
            maximum_source_frames_per_track=100,
            maximum_returned_frames_per_track=101,
        )
