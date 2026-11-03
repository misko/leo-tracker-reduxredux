import numpy as np
from find_profile_minimum import southern_grid,local_offset,best_unique_fits


def test_grid_unique_bounded_and_offset_origin():
    points=southern_grid()
    assert len(points)==len(set(points))==16
    assert all(np.hypot(e,n)<3000 for e,n in points)
    np.testing.assert_allclose(local_offset(37.8,-122.4,37.8,-122.4),[0,0],atol=1e-8)
    east,north=local_offset(0,0,0,1)
    assert abs(east-111195.08)<.1 and abs(north)<1e-8


def test_repeated_position_uses_best_checked_basin_not_first_file():
    poor=dict(parameters=[1.,2.],objective=100.)
    good=dict(parameters=[1.,2.],objective=5.)
    other=dict(parameters=[3.,4.],objective=10.)
    assert best_unique_fits([poor,other,good])==[good,other]
