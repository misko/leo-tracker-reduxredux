"""Rejected replay diagnostics retain exact fields without relaxing equality."""

import json
from types import SimpleNamespace

import pytest

from tools.qualify_scanner_glrt_sdk import _require_result_binding

EXPECTED = dict(
    sequence=3,
    visit=3,
    valid_start=2**53 + 347,
    valid_end=2**53 + 600347,
    rate_hz=5000000,
    rx=1,
    channel=4,
    edge="lower",
    verdict="starlink",
    reason="complete",
    search_window_mask=63,
    search_start=2**53 + 347,
    search_end=2**53 + 600347,
)


@pytest.mark.parametrize("field", EXPECTED)
def test_each_binding_field_still_rejects_and_reports_both_values(field):
    expected = EXPECTED[field]
    actual = expected + 1 if isinstance(expected, int) else expected + "-wrong"
    record = SimpleNamespace(**(EXPECTED | {field: actual}))
    with pytest.raises(ValueError, match="SDK result lost") as error:
        _require_result_binding(record, EXPECTED)
    detail = json.loads(str(error.value).split(": ", 1)[1])
    assert detail == dict(visit=3, differences={field: dict(actual=actual, expected=expected)})


def test_identical_binding_passes_without_diagnostics():
    assert _require_result_binding(SimpleNamespace(**EXPECTED), EXPECTED) is None


def test_worker_busy_is_distinguishable_from_wrong_source_geometry():
    record = SimpleNamespace(
        **(
            EXPECTED
            | dict(
                verdict="unavailable",
                reason="worker_busy",
                search_window_mask=0,
                search_end=EXPECTED["search_start"],
            )
        )
    )
    with pytest.raises(ValueError) as error:
        _require_result_binding(record, EXPECTED)
    detail = json.loads(str(error.value).split(": ", 1)[1])
    assert detail["differences"]["reason"] == dict(actual="worker_busy", expected="complete")
    assert detail["differences"]["search_end"]["actual"] == 2**53 + 347
    assert set(detail["differences"]) == {"verdict", "reason", "search_window_mask", "search_end"}
