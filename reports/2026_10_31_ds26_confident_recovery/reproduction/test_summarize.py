import pytest
from summarize import distance,summarize_values

def test_geodesic_zero_and_known_equator_degree():
    assert distance((0,0),(0,0))==0
    assert distance((0,0),(0,1))==pytest.approx(111195.0802,rel=1e-8)

def test_unavailable_scan_not_scored_zero_and_pooled_denominator():
    rows=[dict(state='complete',error_m=200,baseline_error_m=100,glrt_points=10,associated=6,added_points=1),
          dict(state='complete',error_m=600,baseline_error_m=800,glrt_points=30,associated=12,added_points=0),
          dict(state='unavailable')]
    r=summarize_values(rows)
    assert r['mean_error_m']==400 and r['associated_percent']==45
    assert r['usable']==2 and r['unavailable']==1 and r['added_points']==1
    assert r['worse_over_1m']==1 and r['improved_over_1m']==1
