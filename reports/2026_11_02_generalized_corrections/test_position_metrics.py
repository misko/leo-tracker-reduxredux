"""Postdecision reporting checks; no scientific policy is selected here."""
import numpy as np
from evaluate_positions import error_m, metrics, SITE


def test_truth_coordinate_is_zero_error_only_in_reporting():
    position=((SITE[1]+122.545)*111.32*np.cos(np.deg2rad(37.906)),
              (SITE[0]-37.906)*111.0)
    assert error_m(position)<1e-6


def test_all_fallbacks_remain_in_metric_denominator():
    rows=[dict(error_m=e,change_m=d,stage_accepted=accepted,
               output_source='candidate' if accepted else 'exact_saved_ALGO07',associated_points=100)
          for e,d,accepted in [(400,-100,True),(800,0,False),(1100,100,True)]]
    result=metrics(rows)
    assert result['count']==3 and result['below_500m']==1
    assert result['improved_over50m']==1 and result['regressed_over50m']==1
    assert result['selected_new_endpoint']==2 and result['associated_points']==300
