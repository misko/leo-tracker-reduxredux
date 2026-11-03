import numpy as np
import pytest
from probe_algo03_new_family_position import augment_rows


def proposal(key):
    return dict(component=key,arms=dict(c0=dict(candidates=[dict(candidate_index=8,norad=88,alias=1)])))


def test_restore_unused_curve_without_duplicating_original_row_or_point():
    tracks=[dict(key="a",observation_ids=["1","2"]),dict(key="b",observation_ids=["3","4"])]
    rows=[dict(component="a",candidate_index=1),dict(component="b",candidate_index=2)]
    new,aliases,keep,powers,before,after=augment_rows(rows,[0,0],[True,True,False,False],[1.,.6],tracks,[proposal("b")])
    assert len(new)==2 and new[1]["candidate_index"]==8
    assert aliases==[0,1] and keep.all()
    np.testing.assert_array_equal(powers,[1.,.2])
    assert before=={"1","2"} and after=={"1","2","3","4"}
    assert rows[1]["candidate_index"]==2


def test_active_observation_cannot_be_reused_as_new_family():
    tracks=[dict(key="a",observation_ids=["1","2"])]
    with pytest.raises(ValueError,match="disjoint"):
        augment_rows([dict(component="a")],[0],[True,False],[1.],tracks,[proposal("a")])


def test_new_radio_curved_row_appends_without_changing_original_mask():
    tracks=[dict(key="a",observation_ids=["1","2"]),dict(key="b",observation_ids=["3","4"])]
    rows,aliases,keep,powers,before,after=augment_rows([dict(component="a")],[0],
        [True,False],[.6],tracks,[proposal("b")])
    assert [r["component"] for r in rows]==["a","b"] and aliases==[0,1]
    np.testing.assert_array_equal(keep,[True,False,True,True])
    np.testing.assert_array_equal(powers,[.6,.2])
    assert before=={"1"} and after=={"1","3","4"}
