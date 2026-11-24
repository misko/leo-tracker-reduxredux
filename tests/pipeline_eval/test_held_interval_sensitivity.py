import pytest

from reports.ALGO08.v3.held_interval_sensitivity import interval_sensitivity


def test_omission_uses_clock_bins_including_empty_intervals():
    scores = dict(blocks={"2": 3.0, "4": -2.0, "5": 1.0},
                  first_minus_second_nats=2.0, by_radio={"1": 3.0, "2": -1.0})
    result = interval_sensitivity(scores)
    assert result["10"] == dict(minimum=-1, maximum=4, weakest_start_s=20, first_loses=1, starts=4)
    assert result["30"]["starts"] == 2
    assert result["30"]["minimum"] == 1


@pytest.mark.parametrize("overrides", [dict(first_minus_second_nats=5), dict(by_radio={"1": 0, "2": 0}),
                                       dict(blocks={})])
def test_rejects_inconsistent_evidence(overrides):
    scores = dict(blocks={"0": 3.0, "1": -1.0}, first_minus_second_nats=2.0, by_radio={"1": 2.0, "2": 0.0})
    with pytest.raises(ValueError):
        interval_sensitivity(scores | overrides, widths=(1,))
