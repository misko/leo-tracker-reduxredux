import pytest
from report_support import effective_result, full_values


def test_pending_tail_prevents_full_mean():
    assert full_values([dict(operational={"fitted-c": {"error_km": 1}}),
                        dict(operational=None)], "fitted-c", "error_km") is None


def test_fixed_retention_is_known_without_worker_receipt():
    previous = {"fitted-c": {"error_km": 100}}
    row = effective_result(dict(requested_extra_search=False), previous, None, "digest")
    assert full_values([row], "fitted-c", "error_km") == [100]
    assert row["status"] == "retained_by_frozen_rule"


def test_wrong_protocol_cannot_enter_metrics():
    with pytest.raises(AssertionError):
        effective_result({}, {}, dict(protocol_sha256="wrong"), "expected")
