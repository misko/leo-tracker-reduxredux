import numpy as np
from diagnose_graph_position_pull import curvature


def test_position_curvature_recovers_rotated_quadratic_with_gradient():
    h=np.array([[4.,1.],[1.,2.]]);g=np.array([3.,-2.]);x=np.array([.5,.7])
    r=curvature(lambda z:100+.5*z@h@z+g@z,x)
    np.testing.assert_allclose(r['hessian_per_km2'],h,atol=1e-8)
    np.testing.assert_allclose(r['gradient_per_km'],h@x+g,atol=1e-8)


def test_family_deletion_removes_all_channels_and_predictive_rows_without_mutation():
    from ablate_graph_position_families import omit_family
    original=np.ones(6,bool);rows=[dict(candidate_norad=n) for n in [1,2,1]]
    entries=[dict(norad=1),dict(norad=2)]
    mask,remaining=omit_family(original,rows,[slice(0,2),slice(2,4),slice(4,6)],entries,1)
    np.testing.assert_array_equal(mask,[0,0,1,1,0,0]);assert original.all()
    assert remaining==[entries[1]] and len(entries)==2
