import numpy as np
import pytest
from ds23_stationary_consensus import causal_estimates,spatial_median


def row(case,start,end,position,segment="a"):
    return dict(case=case,cutoff_utc_ns=start,last_observation_utc_ns=end,position=position,stationary_segment=segment)


def test_future_and_overlapping_recordings_cannot_change_earlier_estimates():
    a=row("a",10,30,[1.,2.]);b=row("b",20,35,[3.,4.]);c=row("c",40,45,[5.,6.])
    early=causal_estimates([a,b],"mean",declared_stationary=True)
    full=causal_estimates([c,a,b],"mean",declared_stationary=True)
    np.testing.assert_array_equal(full[1]["estimate"],early[1]["estimate"])
    assert full[1]["used_cases"]==["b"]
    assert full[2]["used_cases"]==["a","b","c"]


def test_stationarity_is_required_and_location_segments_reset_history():
    records=[row("a",10,20,[1.,2.]),row("b",30,40,[7.,8.],"new")]
    with pytest.raises(ValueError,match="stationary"):
        causal_estimates(records,"mean",declared_stationary=False)
    result=causal_estimates(records,"mean",declared_stationary=True)
    assert result[1]["used_cases"]==["b"]
    np.testing.assert_array_equal(result[1]["estimate"],[7.,8.])


def test_history_only_forecast_is_not_marked_a_new_rf_measurement():
    result=causal_estimates([row("a",10,20,[1.,2.]),row("b",30,None,None)],"mean",declared_stationary=True)
    assert result[1]["RF_update"] is False and result[1]["history_points"]==1
    np.testing.assert_array_equal(result[1]["estimate"],[1.,2.])


def test_spatial_median_handles_coincident_points_and_rejects_outlier():
    np.testing.assert_allclose(spatial_median([[0.,0.],[0.,0.],[100.,100.]]),[0.,0.],atol=1e-8)
    np.testing.assert_array_equal(spatial_median([[2.,3.]]),[2.,3.])
