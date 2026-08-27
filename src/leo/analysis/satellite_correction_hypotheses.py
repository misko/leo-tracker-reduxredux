"""Pure bounded builder for joint frozen correction hypotheses."""

from __future__ import annotations

from typing import Any

from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.satellite_pnt import SatelliteCorrectionProductV1
from leo.contracts.satellite_pnt_hypotheses import (
    FrozenCorrectionSourceSlotV1,
    SatelliteCorrectionHypothesisSetV1,
    derive_joint_correction_hypotheses,
)


def build_joint_correction_hypothesis_set(
    *,
    slot_products: tuple[tuple[str, SatelliteCorrectionProductV1], ...],
    jointing_protocol_digest: Sha256Digest,
) -> SatelliteCorrectionHypothesisSetV1:
    """Build the complete exclusivity-conditioned independent-slot family."""

    slots = tuple(
        FrozenCorrectionSourceSlotV1(
            slot_id=slot_id,
            correction_product=SatelliteCorrectionProductV1.model_validate(
                product.model_dump(mode="json")
            ),
        )
        for slot_id, product in sorted(slot_products, key=lambda item: item[0])
    )
    hypotheses = derive_joint_correction_hypotheses(slots)
    values: dict[str, object] = {
        "jointing_protocol_digest": jointing_protocol_digest,
        "source_slots": slots,
        "hypotheses": hypotheses,
        "source_hypothesis_count": len(hypotheses),
    }
    draft_values: dict[str, Any] = {
        **values,
        "content_digest": canonical_digest({"draft": "joint-correction-hypotheses"}),
    }
    draft = SatelliteCorrectionHypothesisSetV1.model_construct(**draft_values)
    payload = draft.model_dump(mode="json", exclude={"content_digest"}, warnings=False)
    return SatelliteCorrectionHypothesisSetV1.model_validate(
        {**payload, "content_digest": canonical_digest(payload)}
    )
