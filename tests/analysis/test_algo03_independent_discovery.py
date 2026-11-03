import numpy as np
import pytest
from probe_algo03_independent_discovery import align_population


def test_nomination_order_changes_preserve_each_observation_mask_and_power():
    tracks=[dict(key="a",observation_ids=["1","2"]),dict(key="b",observation_ids=["3"])]
    old=[dict(component="a"),dict(component="b")]
    keep,powers=align_population(old,old[::-1],tracks,[True,False,True],[.2,1.])
    np.testing.assert_array_equal(keep,[True,True,False])
    np.testing.assert_array_equal(powers,[1.,.2])


def test_different_or_duplicate_population_is_rejected():
    tracks=[dict(key="a",observation_ids=["1"])]
    for rows in ([dict(component="b")],[dict(component="a"),dict(component="a")]):
        with pytest.raises(ValueError):
            align_population([dict(component="a")],rows,tracks,[True],[1.])
