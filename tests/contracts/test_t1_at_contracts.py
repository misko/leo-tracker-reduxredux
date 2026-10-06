"""Published-shape and accounting tests owned by the T1-AT evidence contract."""

import pytest

from leo.contracts.t1_at import T1AtInputV1, T1AtModeV1, T1AtProductV1, T1AtSelectionV1
from tests.analysis.test_t1_at import candidates, mode, source
from tests.storage.test_t1_at import product


def test_v1_roundtrip_and_conditional_scope():
    evidence = source(candidates(20), (mode(100, list(range(20))),))
    assert T1AtInputV1.model_validate_json(evidence.model_dump_json()) == evidence
    result = product()
    assert T1AtProductV1.model_validate_json(result.model_dump_json()) == result
    assert result.candidate_only and not result.identity_claimed


@pytest.mark.parametrize("error", [600.1, -600.1, float("nan"), float("inf")])
def test_mode_errors_must_be_finite_and_inside_gate(error):
    with pytest.raises(ValueError):
        mode(100, [0], error=error)


def test_missing_candidate_and_mismatched_arrays_rejected():
    with pytest.raises(ValueError, match="missing candidate"):
        source(candidates(1), (mode(100, [1]),))
    with pytest.raises(ValueError, match="do not match"):
        T1AtModeV1(catalog_number=100, absolute_timing_s=0, candidate_ids=(0,), residual_hz=())


@pytest.mark.parametrize("change", [dict(assigned=1), dict(unassigned=1), dict(objective=1)])
def test_selection_count_and_objective_cannot_be_invented(change):
    empty = product().arms["fitted-c"].final.model_dump()
    with pytest.raises(ValueError):
        T1AtSelectionV1.model_validate({**empty, **change})


def test_single_rf_arm_is_not_a_valid_product():
    value = product().model_dump()
    del value["arms"]["zero-c"]
    with pytest.raises(ValueError, match="both RF"):
        T1AtProductV1.model_validate(value)


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", 2),
        ("calibration_qualified", False),
        ("timing_convention", "relative-to-fold"),
    ],
)
def test_input_rejects_different_contract_semantics(field, value):
    with pytest.raises(ValueError):
        T1AtInputV1.model_validate({**source((), ()).model_dump(), field: value})
