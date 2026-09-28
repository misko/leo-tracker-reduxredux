from types import SimpleNamespace
import numpy as np
import pytest
from measured_search import representative, search


def evaluator(center):
    return lambda points: tuple(SimpleNamespace(east_km=float(e), north_km=float(n),
        weighted_mse_hz2=10.+(e-center[0])**2+(n-center[1])**2) for e, n in points)


def test_boundary_representatives_are_inside_disk_and_cell():
    for e in range(-450, 451, 100):
        for n in range(-450, 451, 100):
            p = representative(e, n, 100, 250)
            if p is not None:
                assert np.linalg.norm(p) <= 250+1e-10
                assert max(abs(p[0]-e), abs(p[1]-n)) <= 50+1e-10


def test_positive_bowl_refines_interior_and_changes_with_objective():
    a = search(evaluator((-70., -90.)), radius_km=250., budget_points=160)
    b = search(evaluator((70., 90.)), radius_km=250., budget_points=160)
    best = a.global_incumbent
    assert np.hypot(best.east_km+70, best.north_km+90) < 2.
    assert a.finest_evaluations
    pa = {(p.east_km, p.north_km) for p in a.all_evaluations}
    pb = {(p.east_km, p.north_km) for p in b.all_evaluations}
    assert pa != pb
    assert all(x['measured_priority'] >= 10 for x in a.trace if x['event'] == 'pop')
    assert len(pa) <= 160


def test_negative_objective_and_boundary_minimum_are_valid():
    f = lambda points: tuple(SimpleNamespace(east_km=float(e), north_km=float(n),
        weighted_mse_hz2=-1000.+(e-250)**2+n*n) for e, n in points)
    r = search(f, radius_km=250., budget_points=160)
    assert r.global_incumbent.weighted_mse_hz2 < -990
    assert all(np.hypot(p.east_km, p.north_km) <= 250+1e-10 for p in r.all_evaluations)
    with pytest.raises(ValueError, match='initial'):
        search(f, budget_points=1)
