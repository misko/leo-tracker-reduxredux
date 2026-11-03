import numpy as np
import pytest
from probe_ds23_stationary_history_diagnostic import spatial_median,causal_prefix


def test_spatial_median_is_rotation_translation_equivariant_and_robust_to_one_remote_point():
    p=np.array([[1.,1.],[1.1,1.],[1.,1.1],[1.,.9],[100.,100.]])
    x,_=spatial_median(p);assert np.linalg.norm(x-[1,1])<.1
    rotation=np.array([[0.,-1.],[1.,0.]]);shift=np.array([5.,-3.])
    y,_=spatial_median(p@rotation+shift)
    np.testing.assert_allclose(y,x@rotation+shift,atol=1e-7)


def test_changing_future_inputs_cannot_change_a_prefix_estimate():
    records=[dict(case=str(k),captured_utc_ns=k,east_north_km=[k,k*.1]) for k in range(8)]
    before=causal_prefix(records)
    records[-1]['east_north_km']=[1000.,-300.]
    after=causal_prefix(records)
    for a,b in zip(before[:-1],after[:-1],strict=True):
        np.testing.assert_array_equal(a['position_east_north_km'],b['position_east_north_km'])
        assert a['latest_input_utc_ns']==a['captured_utc_ns']


def test_duplicate_times_rejected_and_one_scan_has_no_borrowed_position():
    record=dict(case='one',captured_utc_ns=1,east_north_km=[3.,-4.])
    np.testing.assert_array_equal(causal_prefix([record])[0]['position_east_north_km'],[3.,-4.])
    with pytest.raises(ValueError):causal_prefix([record,dict(record)])
    # A non-unique median interval keeps its midpoint, not its earliest member.
    np.testing.assert_array_equal(spatial_median([[0.,0.],[2.,0.]])[0],[1.,0.])
