import pytest

from leo.analysis.research.graph_position_membership import point_roles


def test_every_original_owner_gets_exactly_one_role():
    observations=[dict(observation_id=str(i)) for i in range(6)]
    tracks=[dict(observation_ids=["0","1","2","3"])]
    result=point_roles(observations,tracks,{"0"},{"1"},{"0","1","2"})
    assert result=={"0":"curved_likelihood","1":"predictive_likelihood","2":"postfit_only",
                    "3":"unassociated_graph","4":"unassociated_outside_graph","5":"unassociated_outside_graph"}


def test_overlapping_or_nonphysical_owners_are_rejected():
    observations=[dict(observation_id="a")]
    with pytest.raises(ValueError):point_roles(observations,[],{"a"},{"a"},{"a"})
    with pytest.raises(ValueError):point_roles(observations,[],set(),set(),{"other"})
    with pytest.raises(ValueError):point_roles(observations,[],{"a"},set(),set())


def test_native_polynomial_does_not_draw_through_alias_wrap():
    import numpy as np
    from leo.analysis.research.graph_position_membership import native_polynomial
    period=227272.72727272726
    times=np.arange(4.)
    values=period-1+times
    native=np.array([values[0],values[1],values[2]-period,values[3]-period])
    track=dict(times=times,values=values,observation_ids=list("abcd"),
               pieces=[dict(start_s=0.,end_s=3.,reference_time_s=1.5,time_scale_s=1.5,
                            coefficients_hz=[period+.5,1.5])])
    raw={key:dict(measured_cfo_hz=value) for key,value in zip("abcd",native,strict=True)}
    actual=native_polynomial(track,raw)[0]
    assert np.isnan(actual[2])
    assert actual[[0,1,3]]==pytest.approx(native[[0,1,3]])
