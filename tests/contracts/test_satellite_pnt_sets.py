from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from leo.contracts.base import ContractModel
from leo.contracts.digests import canonical_digest
from leo.contracts.satellite_pnt import SatelliteCorrectionProductV1
from leo.contracts.satellite_pnt_sets import (
    FrozenSatelliteCorrectionSelectionV1,
    SatelliteCorrectionSetV1,
)
from tests.analysis.test_blinded_doppler_position import _digest, _product


def _seal[ModelT: ContractModel](
    model: type[ModelT], values: dict[str, Any], digest_field: str = "content_digest"
) -> ModelT:
    draft = model.model_construct(**{**values, digest_field: _digest("draft-set")})
    payload = draft.model_dump(mode="json", exclude={digest_field}, warnings=False)
    return model.model_validate({**payload, digest_field: canonical_digest(payload)})


def _single_product(catalog_number: int) -> SatelliteCorrectionProductV1:
    return _product((catalog_number,), oracle=False)


def _selection(slot_index: int, catalog_number: int) -> FrozenSatelliteCorrectionSelectionV1:
    product = _single_product(catalog_number)
    mode = product.modes[0]
    return FrozenSatelliteCorrectionSelectionV1(
        slot_id=f"slot-{slot_index:02d}",
        correction_product=product,
        selected_mode_digest=mode.mode_digest,
        selected_catalog_number=catalog_number,
        selection_evidence_digest=_digest(f"selection-{slot_index}"),
    )


def _set(
    members: tuple[FrozenSatelliteCorrectionSelectionV1, ...] | None = None,
) -> SatelliteCorrectionSetV1:
    selected = members or tuple(_selection(index, 20_001 + index) for index in range(4))
    products = tuple(item.correction_product for item in selected)
    modes = tuple(
        next(mode for mode in product.modes if mode.mode_digest == member.selected_mode_digest)
        for member, product in zip(selected, products, strict=True)
    )
    return _seal(
        SatelliteCorrectionSetV1,
        {
            "selection_authority_digest": _digest("oracle-selection-authority"),
            "members": selected,
            "produced_utc_ns": max(item.produced_utc_ns for item in products),
            "valid_from_utc_ns": max(item.valid_from_utc_ns for item in modes),
            "valid_until_utc_ns": min(item.valid_until_utc_ns for item in modes),
            "downlink_frequency_hz": products[0].downlink_frequency_hz,
        },
    )


def test_correction_set_keeps_simultaneous_slot_probabilities_local() -> None:
    correction_set = _set()

    assert len(correction_set.members) == 4
    assert sum(
        member.correction_product.modes[0].posterior_probability
        for member in correction_set.members
    ) == pytest.approx(4.0)
    assert len({item.selected_catalog_number for item in correction_set.members}) == 4
    assert correction_set.unknown_identity_joint_hypotheses_supported is False
    assert correction_set.receiver_local_state_excluded is True
    solver_safe = correction_set.model_dump_json().lower()
    assert "latitude_deg" not in solver_safe
    assert "longitude_deg" not in solver_safe
    assert "receiver_local_state_digest" not in solver_safe


def test_selection_rejects_wrong_ineligible_or_stale_nested_mode() -> None:
    product = _single_product(20_001)
    mode = product.modes[0]
    with pytest.raises(ValidationError, match="catalogue number"):
        FrozenSatelliteCorrectionSelectionV1(
            slot_id="slot-00",
            correction_product=product,
            selected_mode_digest=mode.mode_digest,
            selected_catalog_number=20_002,
            selection_evidence_digest=_digest("selection"),
        )

    object.__setattr__(mode, "navigation_eligible", False)
    with pytest.raises(ValidationError):
        FrozenSatelliteCorrectionSelectionV1(
            slot_id="slot-00",
            correction_product=product,
            selected_mode_digest=mode.mode_digest,
            selected_catalog_number=20_001,
            selection_evidence_digest=_digest("selection"),
        )


def test_set_rejects_duplicate_catalogue_and_noncanonical_slots() -> None:
    first = _selection(0, 20_001)
    duplicate_catalogue = _selection(1, 20_001)
    with pytest.raises(ValidationError, match="distinct catalogues"):
        _set((first, duplicate_catalogue))

    second = _selection(1, 20_002)
    with pytest.raises(ValidationError, match="canonically ordered"):
        _set((second, first))


def test_set_rejects_false_validity_and_digest_reseal() -> None:
    correction_set = _set()
    payload = correction_set.model_dump(mode="json")
    payload["valid_until_utc_ns"] -= 1
    payload["content_digest"] = canonical_digest(
        {key: value for key, value in payload.items() if key != "content_digest"}
    )
    with pytest.raises(ValidationError, match="validity"):
        SatelliteCorrectionSetV1.model_validate(payload)

    payload = correction_set.model_dump(mode="json")
    payload["selection_authority_digest"] = _digest("altered-authority")
    with pytest.raises(ValidationError, match="digest"):
        SatelliteCorrectionSetV1.model_validate(payload)
