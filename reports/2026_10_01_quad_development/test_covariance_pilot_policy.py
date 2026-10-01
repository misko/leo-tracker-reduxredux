import pytest
from run_covariance_pilot import remaining_budget


def test_original_work_is_charged_without_budget_extension():
    assert remaining_budget(41.5) == 48.5
    assert remaining_budget(80.) == 10.


@pytest.mark.parametrize('cost', [81., -1., float('nan'), float('inf')])
def test_invalid_or_insufficient_budget_rejected(cost):
    with pytest.raises(ValueError):
        remaining_budget(cost)
