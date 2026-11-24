import pytest

from reports.ALGO08.v3.rolling_input_budget import MAX_SLOT, allocation_plan


def test_tracks_existing_growth_and_exact_once_capacity_independently_per_slot():
    plan = allocation_plan([31, 27, 30, 29, 32, 25, 19])
    assert plan["capacities"] == [32, 29]
    assert plan["additional_capacity_for_equal_slots"] == 3
    assert plan["repeated_capacity_on_growth"] == 27 + 31
    assert [e["kind"] for e in plan["events"]] == ["initial", "initial", "reuse", "growth", "growth", "reuse", "reuse"]


@pytest.mark.parametrize("size", (0, -1, MAX_SLOT + 1, 4.5, True))
def test_need_known_positive_eligible_member_sizes(size):
    with pytest.raises(ValueError, match="eligible bounded member"):
        allocation_plan([size])
