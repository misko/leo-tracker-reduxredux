import numpy as np
from orbit_diagnostics import residual_track, raw_prediction, break_alias_connections


def test_partial_residual_track_masks_times_values_and_ids():
    track=dict(times=[1,2,3,4],values=[11,12,13,14],observation_ids=['a','b','c','d'])
    result,mask=residual_track(track,['b','d'])
    assert result['times'].tolist()==[2,4]
    assert result['values'].tolist()==[12,14]
    assert result['observation_ids'].tolist()==['b','d']
    assert mask.tolist()==[False,True,False,True]


def test_native_prediction_exactly_preserves_fitted_residual_despite_alias_lifts():
    native=np.array([25.,-35.,10.]);residual=np.array([1.,-2.,3.])
    pred=raw_prediction({},native,np.array([100025.,99965.,100010.]),dict(residual_hz=residual))
    np.testing.assert_allclose(native-pred,residual)


def test_rendered_lines_break_when_native_alias_changes():
    values=np.array([1.,2.,3.,4.]);native=np.array([1.,-234373.,3.,4.])
    rendered,breaks=break_alias_connections(values,values,native)
    assert breaks.tolist()==[False,True,True,False]
    assert np.isnan(rendered[1:3]).all()
    np.testing.assert_array_equal(values,[1.,2.,3.,4.])


def test_witness_pairing_uses_each_original_observation_once():
    from witness_diagnostics import unique_time_pairs
    pairs=unique_time_pairs([0.,.05,.2,1.,2.],[.04,.19,1.1])
    assert pairs==[(1,0),(2,1),(3,2)]
    assert len({a for a,b in pairs})==len(pairs)
    assert len({b for a,b in pairs})==len(pairs)
