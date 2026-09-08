import pytest

from leo.contracts.scanner_glrt_frame import ScannerGlrtClassificationV1
from leo.contracts.scanner_glrt_session import ScannerGlrtSessionEvidenceV1


def payload():
    result = ScannerGlrtClassificationV1(
        sequence=0,
        visit=0,
        valid_start=10**16,
        valid_end=10**16 + 600000,
        search_start=10**16,
        search_end=10**16,
        confirmation_start=10**16,
        confirmation_end=10**16,
        rate_hz=5000000,
        channel=1,
        edge="lower",
        rx=1,
        verdict="unavailable",
        reason="worker_busy",
        search_window_mask=0,
    )
    return dict(
        session=10**16 + 1,
        generation=2,
        algorithm_sha256="12" * 32,
        configuration_sha256="34" * 32,
        negotiated=True,
        mode="unqualified-evidence",
        source_terminal_attested=True,
        final_received=True,
        expected_results=1,
        dropped_results=0,
        result_sequence_limit=1,
        results=(result.model_dump(),),
        delivery_complete=True,
        classification_complete=False,
        error=None,
    )


def test_unknown_work_can_be_fully_delivered_without_being_classified():
    value = ScannerGlrtSessionEvidenceV1(**payload())
    assert value.delivery_complete and not value.classification_complete
    encoded = value.model_dump_json()
    assert '"session":"10000000000000001"' in encoded
    assert ScannerGlrtSessionEvidenceV1.model_validate_json(encoded) == value


@pytest.mark.parametrize(
    "change",
    [
        {"classification_complete": True},
        {"delivery_complete": False},
        {"final_received": False},
        {"source_terminal_attested": False},
        {"expected_results": 2},
        {"result_sequence_limit": 2},
        {"dropped_results": 1},
        {"negotiated": False},
        {"mode": None},
        {"error": "missing"},
        {"session": 0},
        {"algorithm_sha256": "0" * 64},
        {"configuration_sha256": "0" * 64},
        {"expected_results": True},
        {"negotiated": 1},
        {"unpublished_field": 1},
    ],
)
def test_contract_rejects_inconsistent_completeness_and_identity(change):
    with pytest.raises(ValueError):
        ScannerGlrtSessionEvidenceV1(**(payload() | change))


@pytest.mark.parametrize("change", [{"rx": 0}, {"sequence": 1}, {"visit": 1}])
def test_result_inventory_must_match_source_dwell_range(change):
    data = payload()
    data["results"] = (data["results"][0] | change,)
    with pytest.raises(ValueError):
        ScannerGlrtSessionEvidenceV1(**data)


def test_zero_visit_delivery_is_not_signal_classification():
    data = payload() | {"results": (), "expected_results": 0, "result_sequence_limit": 0}
    value = ScannerGlrtSessionEvidenceV1(**data)
    assert value.delivery_complete and not value.classification_complete
    with pytest.raises(ValueError):
        ScannerGlrtSessionEvidenceV1(**(data | {"classification_complete": True}))


def test_unqualified_mode_cannot_publish_a_negative_classification():
    data = payload()
    record = data["results"][0]
    data["results"] = (
        record
        | {
            "verdict": "no_signal",
            "reason": "complete",
            "search_window_mask": 63,
            "search_end": record["valid_end"],
        },
    )
    data["classification_complete"] = True
    with pytest.raises(ValueError, match="unqualified"):
        ScannerGlrtSessionEvidenceV1(**data)
