import pytest

from leo.contracts.scanner_refinement import (
    ComparisonEvidenceV1,
    ComparisonEvidenceV2,
    ComparisonRowV1,
)
from tests.scanner.refinement_fixtures import comparison_fixture


def test_evidence_rejects_missing_duplicate_and_unscheduled_cases():
    fixture = comparison_fixture().model_dump()
    for rows in (fixture["rows"][:-1], (*fixture["rows"], fixture["rows"][0])):
        with pytest.raises(ValueError):
            ComparisonEvidenceV1.model_validate({**fixture, "rows": rows})
    with pytest.raises(ValueError):
        ComparisonEvidenceV1.model_validate({**fixture, "scheduled_probe_ids": ()})


def test_selected_rank_must_exist_with_measurements():
    row = comparison_fixture().rows[0].model_dump()
    with pytest.raises(ValueError):
        ComparisonRowV1.model_validate({**row, "selected_rank": 8})


def test_native_ten_megasample_contract_preserves_legacy_rate_and_receiver_policy():
    legacy = comparison_fixture().model_dump()
    with pytest.raises(ValueError):
        ComparisonEvidenceV1.model_validate({**legacy, "sample_rate_hz": 10000000})
    native = comparison_fixture(sample_rate_hz=10000000)
    assert native.schema_version == 2
    assert native.selection_policy.endswith("recorded-receivers")
    assert ComparisonEvidenceV2.model_validate(native.model_dump()) == native
    with pytest.raises(ValueError):
        ComparisonEvidenceV2.model_validate({**native.model_dump(), "sample_rate_hz": 5000000})
