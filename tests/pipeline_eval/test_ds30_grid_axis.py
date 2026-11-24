from math import cos, hypot, pi, radians, sin

import pytest

from reports.ALGO08.v3.ds30_grid_axis import (
    MIN_KM, RADIUS_KM, analyze, angular_null, axis_in_metric, bearing_stats, centered, displacement,
    dot, double_direction, transport, weak_axis,
)
from tools.pipeline_eval.scoring import distance_km


def test_weak_metric_axis_of_rotated_known_quadratic_and_isotropy():
    theta = pi/8
    east, north = cos(theta), sin(theta)
    ee, en, nn = east**2+4*north**2, -3*east*north, north**2+4*east**2
    sy = RADIUS_KM*pi/180/111.
    sx = RADIUS_KM*pi/180*cos(radians(60))/111.32
    result = axis_in_metric(ee*sx*sx, nn*sy*sy, en*sx*sy, 60, 0)
    assert result["curvatures_per_km2"] == pytest.approx([1, 4])
    assert abs(dot(result["axis"], [east, north])) == pytest.approx(1.)
    assert axis_in_metric(sx*sx, sy*sy, 0., 60, 0)["state"] == "isotropic"
    assert axis_in_metric(0., 1., 0., 60, 0)["state"] == "nonpositive_curvature"


def test_endpoint_stencil_has_exact_original_sample_and_all_neighbors():
    rows = [dict(east_km=x, north_km=y, latlon=[y/111., x/111.32],
                 scores={"c0": 700 + x*x + y*y*2})
            for x in (-.5, 0., .5) for y in (-.5, 0., .5)]
    grid = dict(points=rows, endpoints={"c0": [0., 0.]}, endpoint_latlon={"c0": [0., 0.]},
                region_center=[0., 0.])
    assert abs(weak_axis(grid, "c0")["axis"][0]) == pytest.approx(1)
    assert weak_axis(grid | dict(points=rows[:-1]), "c0")["state"] == "missing_stencil"
    assert weak_axis(grid | dict(endpoint_latlon={"c0": [0.001, 0.]}), "c0")["state"] == "unbound_endpoint"


def test_transport_roundtrip_and_metric_distance():
    assert transport((1., 2.), (0., 0.), (0., 90.)) == pytest.approx((1., 2.))
    p, q = (37.0, -123.), (37.9, -122.)
    assert transport(transport((2., -1.), p, q), q, p) == pytest.approx((2., -1.))
    assert hypot(*displacement(p, q, (37.7, -122.5))) == pytest.approx(distance_km(p, q), rel=1e-13)
    assert displacement(p, p, (37.7, -122.5)) == (0., 0.)


def test_bearing_null_preserves_common_direction_and_axis_sign():
    east = double_direction((1., 0.))
    north = double_direction((0., 1.))
    assert east == double_direction((-3., 0.))
    bias = angular_null([east, east, east], [east, east, east])
    assert bias["mean_cos2"] == bias["exact_null_mean"] == 1.
    assert bias["upper_tail_rank"] == 1.
    matched = angular_null([east, north], [east, north])
    assert matched["exact_null_mean"] == 0.
    assert matched["null_middle_95"] == [-1., 1.]
    assert .47 < matched["upper_tail_rank"] < .53
    stats = bearing_stats([(1., 0.), (0., 1.)], [(-3., 0.), (4., 0.)])
    assert stats["median_acute_deg"] == 45. and stats["median_perpendicular_km"] == 2.


def test_bias_removal_and_unresolved_or_short_directions_reported():
    values = ((2., 1.), (2., -1.))
    residuals, bias = centered(values)
    assert residuals == [(0., 1.), (0., -1.)] and bias == 2.
    valid = dict(state="valid", axis=(1., 0.))
    arms = [dict(candidate_axis=valid, installed_axis=valid, to_installed=d) for d in (*values, (.5*MIN_KM, 0.), None)]
    arms.append(dict(candidate_axis={"state": "isotropic"}, installed_axis=valid, to_installed=(2., 0.)))
    stats = analyze([{"arms": {"c0": arm}} for arm in arms], "c0", "to_installed")
    assert stats["candidate"]["n"] == stats["centered_candidate"]["n"] == 2
    assert stats["centered_candidate"]["mean_cos2"] == -1
    assert stats["exclusions"] == {"short_displacement": 1, "no_shared_fix": 1, "candidate_isotropic": 1}
