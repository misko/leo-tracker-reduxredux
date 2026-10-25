"""The diagnostic must reproduce strict original screen boundaries."""
import numpy as np
from fallback_gates import screen_failures


def test_original_boundary_passes_and_signed_acf_is_checked_absolutely():
    n=100
    d=dict(mean_z=3.,slope_z=3.,quadratic_bic_gain=10.,maximum_step_z=4.,lag1_acf=-4/np.sqrt(n))
    assert screen_failures('conditional',d,n)==[]
    d['lag1_acf']=-.41
    rows=screen_failures('conditional',d,n)
    assert len(rows)==1 and rows[0]['criterion']=='conditional_lag1_acf'
    assert abs(rows[0]['excess']-.01)<1e-12


def test_multiple_original_failures_are_not_replaced_by_one_label():
    d=dict(mean_z=1.,slope_z=3.1,quadratic_bic_gain=12.,maximum_step_z=4.3,lag1_acf=0.)
    reasons={r['criterion'] for r in screen_failures('profile',d,40)}
    assert reasons=={'profile_slope_z','profile_quadratic_bic_gain','profile_maximum_step_z'}
