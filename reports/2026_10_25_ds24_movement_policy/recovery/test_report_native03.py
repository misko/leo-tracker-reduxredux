import numpy as np
import pytest
from report_native03 import native_source, PERIOD


def test_source_coordinates_use_native_ID_mapping_not_wrapped_graph_values():
    track=dict(key='t',receiver=1,channel=2,observation_ids=['b','a'],times=[1.,2.],values=[1.,2.])
    lookup={'a':dict(receiver=1,channel=2,time_s=2.,measured_cfo_hz=-300000.),
        'b':dict(receiver=1,channel=2,time_s=1.,measured_cfo_hz=-300100.)}
    points=native_source(track,[True,True],lookup,True)
    assert [v['plotted_CFO_hz'] for v in points]==[-300100.,-300000.]
    assert all(v['recovered_source'] for v in points)
    assert not points[1]['line_break_before']


def test_alias_jumps_are_not_joined_and_wrong_native_ownership_fails():
    track=dict(key='t',receiver=1,channel=2,observation_ids=['a','b'],times=[1.,2.])
    lookup={'a':dict(receiver=1,channel=2,time_s=1.,measured_cfo_hz=0.),
        'b':dict(receiver=1,channel=2,time_s=2.,measured_cfo_hz=PERIOD)}
    assert native_source(track,[True,True],lookup,False)[1]['line_break_before']
    lookup['b']['receiver']=2
    with pytest.raises(ValueError,match='owner mismatch'):native_source(track,[True,True],lookup,False)
