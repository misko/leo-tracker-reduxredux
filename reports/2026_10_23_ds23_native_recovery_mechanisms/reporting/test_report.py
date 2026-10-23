import math
import report


def test_position_error_matches_frozen_helper():
    for point in (report.oracle.REFERENCE,(37.84,-122.48),(38,-122)):
        assert report.position_error(point)==report.oracle.position_error(point)
    assert report.position_error(report.oracle.REFERENCE)==0


def test_failed_fit_never_becomes_position():
    fit={'endpoint_latlon':report.oracle.REFERENCE,'endpoint_east_north_km':[0,0]}
    for status in ('failed','pending','error'):
        assert report.row('x','y','c0',fit,status)['error_km'] is None


def test_completed_nonfinite_rejected():
    import pytest
    with pytest.raises(ValueError):
        report.row('x','y','c0',{'endpoint_latlon':[math.nan,0]})


def test_per_arm_slack_qualification_and_extended_association():
    fit={'endpoint_latlon':report.oracle.REFERENCE,'endpoint_east_north_km':[0,0],
         'gate_slacks':{'lag1':-.001},'active_points':2,'predictive_points':1}
    cov={'associated':4,'total_GLRT':5,'accepted_observation_ids':['a','b','c','d']}
    result=report.row('x','y','c0',fit,cov=cov)
    assert result['qualified'] is False
    assert result['likelihood_points_minus_associated']==-1
    assert 'offered_minus_accepted_points' not in result
