import math

import pytest

from leo.analysis.position_grid import sample_position_grid


def test_both_calibration_arms_share_the_grid_and_preserve_their_known_minima():
    endpoints={'c0':[1.,-2.],'fitted_c':[1.2,-2.1]}
    visits={a:[] for a in endpoints}
    def score(arm,xy):
        visits[arm].append(xy)
        return sum((v-w)**2 for v,w in zip(xy,endpoints[arm],strict=True))
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
    def score(arm,xy):
        elapsed[0]+=3
        return 10.
    grid=sample_position_grid(score,dict(c0=[1.,2.],fitted_c=[1.1,2.1]),
                              maximum_seconds=5.,clock=lambda:elapsed[0])
    assert not grid['complete'] and grid['evaluated_points']==1
    assert grid['points'][0]['scores']==dict(c0=10.,fitted_c=10.)


def test_nonfinite_scores_are_unscored_instead_of_false_minima():
    grid=sample_position_grid(lambda arm,x:math.inf if arm=='c0' else 12.,
                             dict(c0=[0.,0.],fitted_c=[0.,0.]),coarse_size=2,local_size=2)
    assert all(p['scores']['c0'] is None and p['scores']['fitted_c']==12. for p in grid['points'])


def test_batches_preserve_full_grid_and_numeric_failures_in_original_order():
    from leo.operations.localization_v3_parallel import map_grid_batches

    def score(arm, xy):
        if arm == 'c0' and xy[0] < 0:
            raise ArithmeticError('invalid score')
        return math.sin(xy[0]) + math.cos(xy[1]) + (arm == 'fitted_c')

    kwargs = dict(clock=lambda: 0., coarse_size=5, local_size=3)
    endpoints = dict(c0=[1., 2.], fitted_c=[-1., 3.])
    serial = sample_position_grid(score, endpoints, **kwargs)
    parallel = sample_position_grid(score, endpoints, map_batches=map_grid_batches, **kwargs)
    assert parallel == serial


def test_expired_middle_batch_keeps_only_contiguous_paired_prefix():
    elapsed = [0.]
    def clock():
        return elapsed[0]
    def dispatch(operation, chunks):
        # The last chunk may finish first; publication must not jump over a
        # timed-out middle chunk to include those already completed locations.
        last = operation(chunks[2])
        first = operation(chunks[0])
        elapsed[0] = 30.
        middle = operation(chunks[1])
        return [first, middle, last]
    endpoints = dict(c0=[1., 2.], fitted_c=[1., 3.])
    full = sample_position_grid(lambda a, x: 1., endpoints, clock=clock)
    partial = sample_position_grid(lambda a, x: 1., endpoints, clock=clock, map_batches=dispatch)
    count = (full['planned_points'] + 2) // 3
    assert not partial['complete'] and partial['evaluated_points'] == count
    assert partial['points'] == full['points'][:count]


def test_batch_transport_failure_is_not_a_missing_scientific_score():
    def dispatch(operation, chunks):
        raise RuntimeError('transport failed')
    with pytest.raises(RuntimeError, match='transport failed'):
        sample_position_grid(lambda a, x: 1., dict(c0=[0., 0.], fitted_c=[0., 0.]),
                             map_batches=dispatch)
