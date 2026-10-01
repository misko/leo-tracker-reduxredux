import numpy as np
import pytest
from run_shared_window_pilot import budget,PILOT,BOUNDARY


def test_size_budget_charges_all_prior_work():
    assert budget(2,106.211389)==pytest.approx((180,73.788611))
    assert budget(4,170)==(360,190)
    assert budget(2,181)==(180,0)
    for size,cost in [(1,0),(3,0),(2,-1),(4,np.nan)]:
        with pytest.raises(ValueError):budget(size,cost)


def test_failure_selected_case_is_distinct_from_six_metadata_first_cases():
    assert len(PILOT)==len(set(PILOT))==7 and PILOT[0]==BOUNDARY
    assert all('-B01-' in unit for unit in PILOT[1:])
