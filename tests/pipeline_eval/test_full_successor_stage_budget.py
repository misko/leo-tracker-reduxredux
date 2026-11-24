import pytest

from reports.ALGO08.v3.full_successor_stage_budget import elapsed_budget


def test_nested_callbacks_are_subtracted_only_once():
    r = elapsed_budget(20, 15, 5, 8, 1)
    assert r["gap_s"] == 5
    assert r["remaining_s"] == 2
    assert r["minimum_savings_outside_detector_s"] == 4
    assert r["fraction_needed_from_acquisition_and_publication"] == 5/13
    assert r["speedup_if_acquisition_and_publication_each_halved"] == 20/8.5


@pytest.mark.parametrize("values", [(20, 15, 2, 13, 3), (20, 15, 4, 12, 2),
                                     (0, 12, 8, 2, 3), (float("nan"), 12, 8, 2, 3)])
def test_inconsistent_stage_clocks_rejected(values):
    with pytest.raises(ValueError):
        elapsed_budget(*values)
