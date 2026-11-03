from report_ds23_dbg01_iteration_003 import result_row
from report_ds23_curve_guard_confirmation import summarize, METHODS
import pytest


def test_report_distinguishes_association_count_from_likelihood_utilization():
    fit=dict(active_points=502,predictive_points=64,endpoint_latlon=[37.849061591561885,-122.48574968092912],RMS_hz=114.)
    inventory=dict(associated=584,total_GLRT=1106,percent=100*584/1106,
        associated_tracks=26,predictive_points=64,accepted_observation_ids=['a','b'])
    result=result_row('case','method','fitted_c',fit,inventory,dict(accepted_observation_ids=['a']))
    assert result['total_points_in_position']==566
    assert result['associated_but_not_used']==18
    assert result['original_accepted_points_lost']==0
    assert result['selected_by_GPS'] is False


def test_confirmation_aggregation_keeps_fallback_scans_and_distinguishes_pooled_coverage():
    rows=[]
    for method in METHODS:
        for arm in ['c0','fitted_c']:
            for error,associated,total in [(1.,5,10),(3.,90,100)]:
                rows.append(dict(method=method,arm=arm,position_error_km=error,all_GLRT=total,
                    associated_points=associated,associated_percent=100*associated/total,RMS_hz=40.,
                    original_accepted_points_lost=0))
    summary=summarize(rows)
    assert len(summary)==6
    for r in summary:
        assert r['scans']==2
        assert r['mean_error_km']==2.
        assert r['median_error_km']==2.
        assert r['pooled_association_percent']==pytest.approx(100*95/110)
        assert r['mean_scan_association_percent']==70.
