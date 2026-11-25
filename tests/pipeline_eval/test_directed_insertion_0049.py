import pytest

from reports.ALGO08.v3 import directed_insertion_0049 as check


def test_complete_native_tuple_and_exact_margin_without_reference(monkeypatch):
    values = [0,13299,-.237,-712101.374,.81162,.03172]
    factor = check.full_native_factor(values)
    assert [factor[key] for key in check.ABI] == values
    assert set(factor) == check.FACTOR_FIELDS
    assert factor["fractional_margin"] == values[4]-values[5]
    assert factor["passed_fractional_margin_gate"] is True


@pytest.mark.parametrize("values", [
    [1,113,-.1,50.,.5,.1],
    [0,13_333,-.1,50.,.5,.1],
    [0,113,-.1,float("nan"),.5,.1],
    [0,113,-.1,50.,.12,.10],
])
def test_incomplete_invalid_or_below_gate_native_values_fail_closed(values):
    with pytest.raises(ValueError,match="complete gated native factor"):
        check.full_native_factor(values)
