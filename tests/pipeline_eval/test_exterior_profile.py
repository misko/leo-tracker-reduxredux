import numpy as np
import pytest

from leo.analysis.localization_v3.region import SearchRegion
from tools.pipeline_eval.variants.experimental.exterior_profile import (
    ARMS, WIDTH_FRACTIONS, evaluate, face_points,
)


def test_width_relative_face_schedule_and_mirror():
    endpoints = dict(zip(ARMS, ((4.5, 3), (-2, 5)), strict=True))
    points = face_points(10, endpoints)
    assert {p["face"] for p in points} == {"east", "west", "north", "south"}
    assert len({p["xy_km"] for p in points}) == len(points)
    for point in points:
        norm = max(map(abs, point["xy_km"]))
        if point["side"] == "exterior":
            assert norm == pytest.approx(5 + point["beyond_face_km"])
        else:
            assert norm <= 5
    assert {p["beyond_face_km"] for p in points if p["side"] == "exterior"} == {
        x * 10 for x in WIDTH_FRACTIONS
    }
    for x, y in ((5 + 10 / 32, 3), (5 - 10 / 32, 3), (-(5 + 10 / 32), 3)):
        assert any(p["xy_km"] == (x, y) for p in points)
    doubled = {a: tuple(2 * x for x in xy) for a, xy in endpoints.items()}
    assert [p["xy_km"] for p in face_points(20, doubled)] == [
        tuple(2 * x for x in p["xy_km"]) for p in points
    ]


def test_common_geometry_separates_the_two_profiles_and_keeps_failures():
    region = SearchRegion((42, -19), width_km=16)
    constrained = dict(c0=(8, 1), fitted_c=(8, 1))
    optima = dict(c0=(8.5, 1), fitted_c=(7.5, 1))

    def score(arm, xy):
        return np.sum((xy - optima[arm]) ** 2)

    scores = {arm: score(arm, np.array(constrained[arm])) for arm in ARMS}
    seed = dict(east_km=8, north_km=1, latlon=region.latlon((8, 1)), scores=scores, failures={})
    grid = dict(points=[seed], endpoints=constrained)
    queried = []

    def measured(arm, xy):
        queried.append((arm, tuple(xy)))
        if tuple(xy) == (40, 40) and arm == "fitted_c":
            raise ValueError("native domain failure")
        return score(arm, xy)

    result = evaluate(region, grid, measured)
    assert [p for a, p in queried if a == "c0"] == [p for a, p in queried if a == "fitted_c"]
    zero, fitted = (result["arms"][a] for a in ARMS)
    assert zero["inside_minus_outside"] > 0
    assert zero["outside_best"]["xy_km"] == (8.5, 1)
    assert fitted["inside_minus_outside"] < 0
    assert fitted["inside_best"]["xy_km"] == (7.5, 1)
    assert fitted["failed_points"] == 1
    assert zero["failed_points"] == 0
