import pytest

from review_ds23_0268_geometry import group_geometry


def point(oid='a', arm='c0', **changes):
    return dict(arm=arm, observation_id=oid, component='track', norad=53923,
        receiver=2, time_s=1., nominal_elevation_deg=60.,
        nominal_off_axis_deg=35., fitted_elevation_deg=59.,
        fitted_off_axis_deg=36., direction_correction_deg=1., **changes)


def test_geometry_grouping_counts_each_arm_and_preserves_sky_limits():
    rows = [point(), point('b'), point(arm='fitted_c')]
    rows[1].update(time_s=2., nominal_off_axis_deg=46., fitted_elevation_deg=-1.)
    grouped = group_geometry(rows)
    assert len(grouped) == 2
    c0 = next(r for r in grouped if r['arm'] == 'c0')
    assert c0['points'] == 2
    assert c0['tracks'] == 1
    assert c0['nominal_outside_45deg'] == 1
    assert c0['below_fitted_horizon'] == 1
    assert c0['below_nominal_horizon'] == 0
    assert c0['minimum_fitted_elevation_deg'] == -1.
    assert c0['maximum_nominal_off_axis_deg'] == 46.


def test_duplicate_measurement_cannot_be_hidden_in_two_satellite_families():
    a, b = point(), point()
    b['norad'] = 67953
    with pytest.raises(ValueError, match='duplicate original measurement'):
        group_geometry([a, b])
