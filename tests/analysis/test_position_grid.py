import math

from leo.analysis.position_grid import sample_position_grid


def test_both_calibration_arms_share_the_grid_and_preserve_their_known_minima():
    endpoints={'c0':[1.,-2.],'fitted_c':[1.2,-2.1]}
    visits={a:[] for a in endpoints}
    def score(arm,xy):
        visits[arm].append(xy)
        return sum((v-w)**2 for v,w in zip(xy,endpoints[arm]))
    grid=sample_position_grid(score,endpoints,coarse_size=5,local_size=3)
    assert grid['complete'] and grid['evaluated_points']==grid['planned_points']
    assert visits['c0']==visits['fitted_c']
    assert all(abs(p['east_km'])<=12.5 and abs(p['north_km'])<=12.5 for p in grid['points'])
    for arm in endpoints:
        best=min(grid['points'],key=lambda p:p['scores'][arm])
        assert [best['east_km'],best['north_km']]==endpoints[arm]
        assert best['scores'][arm]==0
    assert endpoints=={'c0':[1.,-2.],'fitted_c':[1.2,-2.1]}


def test_time_budget_keeps_whole_paired_locations_and_marks_partial_grid():
    elapsed=[0.]
    def score(arm,xy):elapsed[0]+=3;return 10.
    grid=sample_position_grid(score,dict(c0=[1.,2.],fitted_c=[1.1,2.1]),
                              maximum_seconds=5.,clock=lambda:elapsed[0])
    assert not grid['complete'] and grid['evaluated_points']==1
    assert grid['points'][0]['scores']==dict(c0=10.,fitted_c=10.)


def test_nonfinite_scores_are_unscored_instead_of_false_minima():
    grid=sample_position_grid(lambda arm,x:math.inf if arm=='c0' else 12.,
                             dict(c0=[0.,0.],fitted_c=[0.,0.]),coarse_size=2,local_size=2)
    assert all(p['scores']['c0'] is None and p['scores']['fitted_c']==12. for p in grid['points'])
