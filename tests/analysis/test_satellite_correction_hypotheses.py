from __future__ import annotations

import math
from typing import Any

import pytest
from pydantic import ValidationError

from leo.analysis.satellite_correction_hypotheses import (
    build_joint_correction_hypothesis_set,
)
from leo.contracts.base import ContractModel
from leo.contracts.digests import canonical_digest
from leo.contracts.satellite_pnt import (
    SatelliteCorrectionProductV1,
    VerifiedTleMemberV1,
)
from leo.contracts.satellite_pnt_hypotheses import SatelliteCorrectionHypothesisSetV1
from tests.analysis.test_blinded_doppler_position import _digest, _mode, _product


def _seal[ModelT: ContractModel](
    model: type[ModelT], values: dict[str, Any], digest_field: str = "content_digest"
) -> ModelT:
    draft = model.model_construct(**{**values, digest_field: _digest("joint-draft")})
    payload = draft.model_dump(mode="json", exclude={digest_field}, warnings=False)
    return model.model_validate({**payload, digest_field: canonical_digest(payload)})


def _reweighted_product(
    catalog_numbers: tuple[int, ...],
    probabilities: tuple[float, ...],
    *,
    unassigned_probability: float,
    lineage: str,
) -> SatelliteCorrectionProductV1:
    assert len(catalog_numbers) == len(probabilities)
    assert math.isclose(
        math.fsum(probabilities) + unassigned_probability,
        1.0,
        rel_tol=0.0,
        abs_tol=1e-12,
    )
    base = _product(catalog_numbers, oracle=False)
    modes = tuple(
        _mode(catalog_number, probability=probability, oracle=False)
        for catalog_number, probability in zip(catalog_numbers, probabilities, strict=True)
    )
    payload = base.model_dump(mode="json")
    payload.update(
        {
            "calibration_evidence_digest": _digest(f"calibration-{lineage}"),
            "association_hypothesis_digest": _digest(f"association-{lineage}"),
            "modes": tuple(item.model_dump(mode="json") for item in modes),
            "verified_tle_members": tuple(
                VerifiedTleMemberV1(
                    catalog_number=item.catalog_number,
                    selected_element_digest=item.selected_element_digest,
                    element_epoch_utc_ns=item.element_epoch_utc_ns,
                ).model_dump(mode="json")
                for item in modes
            ),
            "unassigned_probability": unassigned_probability,
        }
    )
    payload.pop("content_digest")
    return _seal(SatelliteCorrectionProductV1, payload)


def _family() -> SatelliteCorrectionHypothesisSetV1:
    slot_a = _reweighted_product(
        (30_001, 30_002),
        (0.6, 0.3),
        unassigned_probability=0.1,
        lineage="slot-a",
    )
    slot_b = _reweighted_product(
        (30_001, 30_003),
        (0.2, 0.7),
        unassigned_probability=0.1,
        lineage="slot-b",
    )
    return build_joint_correction_hypothesis_set(
        slot_products=(("slot-b", slot_b), ("slot-a", slot_a)),
        jointing_protocol_digest=_digest("jointing-protocol"),
    )


def test_exact_joint_family_preserves_unassigned_and_excludes_duplicate_catalogue() -> None:
    family = _family()

    assert tuple(item.slot_id for item in family.source_slots) == ("slot-a", "slot-b")
    assert family.source_hypothesis_count == 8
    assert len(family.hypotheses) == 8
    assert math.fsum(item.posterior_probability for item in family.hypotheses) == pytest.approx(1.0)
    assert not any(
        tuple(assignment.selected_catalog_number for assignment in item.assignments)
        == (30_001, 30_001)
        for item in family.hypotheses
    )
    all_null = next(item for item in family.hypotheses if not item.active_catalog_numbers)
    assert all_null.posterior_probability == pytest.approx(0.01 / 0.88)
    best = family.hypotheses[0]
    assert best.active_catalog_numbers == (30_001, 30_003)
    assert best.posterior_probability == pytest.approx(0.42 / 0.88)
    assert family.slot_posterior_independence_assumed is True
    assert family.shared_calibration_nuisance_jointly_modeled is False
    assert family.identity_claimed is False


def test_joint_family_is_input_permutation_invariant() -> None:
    family = _family()
    reversed_family = build_joint_correction_hypothesis_set(
        slot_products=tuple(
            reversed(tuple((item.slot_id, item.correction_product) for item in family.source_slots))
        ),
        jointing_protocol_digest=family.jointing_protocol_digest,
    )

    assert reversed_family.content_digest == family.content_digest


def test_contract_rejects_truncation_probability_poison_and_stale_nested_product() -> None:
    family = _family()
    payload = family.model_dump(mode="json")
    payload["hypotheses"] = payload["hypotheses"][:-1]
    payload["source_hypothesis_count"] -= 1
    payload["content_digest"] = canonical_digest(
        {key: value for key, value in payload.items() if key != "content_digest"}
    )
    with pytest.raises(ValidationError, match="count|truncated"):
        SatelliteCorrectionHypothesisSetV1.model_validate(payload)

    payload = family.model_dump(mode="json")
    payload["hypotheses"][0]["posterior_probability"] *= 0.5
    payload["content_digest"] = canonical_digest(
        {key: value for key, value in payload.items() if key != "content_digest"}
    )
    with pytest.raises(ValidationError, match="probability|inventory"):
        SatelliteCorrectionHypothesisSetV1.model_validate(payload)

    product = family.source_slots[0].correction_product
    object.__setattr__(product.modes[0], "posterior_probability", 0.01)
    with pytest.raises(ValidationError, match="digest|sum"):
        build_joint_correction_hypothesis_set(
            slot_products=(("slot-a", product),),
            jointing_protocol_digest=_digest("stale-product"),
        )


def test_exact_family_fails_before_unbounded_cartesian_enumeration() -> None:
    large = tuple(
        (
            f"slot-{index}",
            _reweighted_product(
                tuple(40_000 + index * 10 + item for item in range(5)),
                (0.15, 0.15, 0.15, 0.15, 0.15),
                unassigned_probability=0.25,
                lineage=f"large-{index}",
            ),
        )
        for index in range(5)
    )
    with pytest.raises(ValueError, match="work bound"):
        build_joint_correction_hypothesis_set(
            slot_products=large,
            jointing_protocol_digest=_digest("large-family"),
        )
