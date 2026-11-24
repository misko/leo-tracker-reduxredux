"""Spherical transport and all-attempt coverage for the offline calibration study."""

import pytest

from reports.ALGO08.v3.calibration_transport import (
    distance_m, endpoints, paired_delta, sphere_vector, spherical_coordinate, threshold, transfer,
)


def test_identity_transport_preserves_nonzero_source_arc_and_zero_correction():
    zero, fitted, remote = (37.9, -122.55), (37.91, -122.548), (-35., 18.)
    assert distance_m(transfer(zero, fitted, zero), fitted) < 1e-7
    assert transfer(zero, zero, remote) == remote
    shifted = transfer(zero, fitted, remote)
    assert distance_m(remote, shifted) == pytest.approx(distance_m(zero, fitted), abs=1e-7)
    assert distance_m(transfer(remote, shifted, zero), fitted) < 1e-7


def test_transport_crosses_the_date_line_in_the_correct_direction():
    actual = transfer((0., 179.999), (0., -179.998), (0., 179.9995))
    assert actual == pytest.approx((0., -179.9975), abs=1e-12)


@pytest.mark.parametrize("zero,fitted,target", [
    ((0., 0.), (0., 180.), (4., 8.)),
    ((0., 0.), (0., 10.), (0., 180.)),
    ((90., 20.), (85., 20.), (-90., 80.)),
])
def test_antipodal_tangent_or_transport_is_ambiguous(zero, fitted, target):
    with pytest.raises(ValueError, match="unique shortest arc|antipodal"):
        transfer(zero, fitted, target)


def test_rotating_a_synthetic_site_preserves_transferred_endpoint_and_error():
    def rotate(point):
        x, y, z = sphere_vector(point)
        return spherical_coordinate((z, -y, x))

    zero, fitted, target = (37.9, -122.55), (37.91, -122.548), (38.0, -121.9)
    survey = (38.045, -121.94)
    actual = transfer(zero, fitted, target)
    rotated = transfer(*(rotate(p) for p in (zero, fitted, target)))
    assert distance_m(rotate(actual), rotated) < 1e-7
    assert distance_m(rotate(survey), rotated) == pytest.approx(distance_m(survey, actual), abs=1e-7)


def test_unshared_fixes_keep_observed_endpoints_and_full_coverage_denominator():
    prior = {"c0": {"latlon": (0., .01)}, "fitted_c": {"latlon": (0., .009)}}
    empty = {"c0": {"latlon": None}, "fitted_c": {"latlon": None}}
    pair = {"installed": {"arms": empty}, "successor": {"arms": prior}}
    result = endpoints(pair)
    assert result["installed_with_successor_delta"] is None
    assert result["successor_with_installed_delta"] == prior["fitted_c"]["latlon"]
    changes = {"a": (None, 500.), "b": (998., 1001.), "c": (1990., 1900.), "d": (None, None)}
    assert threshold(changes, 1000) == dict(before=1, after=1, gained=["a"], lost=["b"])
    assert threshold(changes, 2000) == dict(before=2, after=3, gained=["a"], lost=[])
    assert paired_delta(changes.values()) == dict(n=2, mean=-43.5, median=-43.5, median_abs=46.5,
                                                  improved=1, worsened=1, equal=0)
