"""Geometry and packaged source coverage for the optional longitude chart."""

from math import cos, radians

import numpy as np
import pytest

from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km
from tools.pipeline_eval.qualification import cavity_longitude_trial as trial
from tools.pipeline_eval.qualification import cavity_payload
from tools.pipeline_eval.variants import cavity_longitude as geometry


@pytest.mark.parametrize("latitude", (0.0, 36.0, 79.0, -79.0))
@pytest.mark.parametrize("sign", (1, -1))
def test_local_chart_crosses_the_dateline_with_correct_enu_orientation(latitude, sign):
    center = (latitude, sign * 179.999)
    scale = 111.32 * cos(radians(latitude))
    wanted = (sign * 0.8, 0.4)
    point = geometry.local_latlon(center, scale, wanted)
    assert -180 <= point[1] < 180
    assert sign * point[1] < 0
    assert geometry.local_native_point(center, scale, point) == pytest.approx(wanted, abs=2e-11)

    independent = ecef_to_enu_matrix(*center) @ (
        geodetic_to_ecef_km(*point, 0) - geodetic_to_ecef_km(*center, 0)
    )
    assert independent[:2] == pytest.approx(wanted, abs=0.01)
    assert abs(independent[2]) < 0.001


def test_two_chart_origins_across_dateline_remain_neighbours():
    screen = (36.0, -179.99)
    tile = (36.0, 179.99)
    zone = 111.32 * cos(radians(36.0))
    point = geometry.local_latlon(tile, zone, (0.5, -0.3))
    distance = geometry.local_native_point(screen, zone, point)
    assert distance == pytest.approx((0.5 - 0.02 * zone, -0.3))
    assert geometry.local_latlon(screen, zone, distance) == pytest.approx(point, abs=3e-13)
    geometry.validate_geometry(tile, screen, 25)


def test_linear_legacy_chart_is_exact_away_from_the_seam():
    center = (37.906, -122.545)
    screen = (37.85, -122.48)
    scale = 111.32 * np.cos(np.deg2rad(center[0]))
    screen_scale = 111.32 * np.cos(np.deg2rad(screen[0]))
    x, y = -12.5, 12.5
    legacy = (center[0] + y / 111.0, center[1] + x / scale)
    assert geometry.local_latlon(center, scale, (x, y)) == legacy
    assert tuple(geometry.local_native_point(screen, screen_scale, legacy)) == (
        (legacy[1] - screen[1]) * screen_scale,
        (legacy[0] - screen[0]) * 111.0,
    )


@pytest.mark.parametrize(
    "tile,screen,width",
    [
        ((89.98, 179), (89.9, 179), 25),
        ((36, 179), (36, 179), 26),
        ((36, 179), (36, -170), 25),
        ((36, 179), (36, float("inf")), 25),
    ],
)
def test_unsupported_geometries_are_rejected(tile, screen, width):
    with pytest.raises(ValueError):
        geometry.validate_geometry(tile, screen, width)


def test_release_touches_only_the_three_coordinate_sites_and_argument_validation():
    folder = trial.REPORT.with_name("cavity-payload")
    manifest = trial._read(folder / "package.json")
    base = cavity_payload.read_bundle(folder / "receiver-source.tar.gz", manifest["files"])
    wrapped = trial.overlay(base)
    assert set(wrapped) - set(base) == {trial.HELPER}
    assert {name for name in base if base[name] != wrapped[name]} == {
        trial.REGION,
        trial.SCAN,
        trial.ENTRY,
    }
    for name in (trial.HELPER, trial.REGION, trial.SCAN, trial.ENTRY):
        compile(wrapped[name], name, "exec")
