"""Geographic arithmetic checks; no new scientific or geographic results are read."""
import numpy as np

from report import CENTER, EVALUATION_SITE, coordinates, error_km


def test_original_regional_coordinate_convention():
    np.testing.assert_array_equal(coordinates([0.,0.]),CENTER)
    np.testing.assert_allclose(coordinates([111.32*np.cos(np.radians(CENTER[0])),111.]),CENTER+1,rtol=0,atol=1e-13)


def test_spherical_distance_zero_antipode_and_longitude_wrap():
    assert error_km(EVALUATION_SITE)==0.
    antipode=np.array([-EVALUATION_SITE[0],EVALUATION_SITE[1]+180])
    np.testing.assert_allclose(error_km(antipode),6371*np.pi,rtol=1e-8)
    np.testing.assert_allclose(error_km(EVALUATION_SITE+[0.,360.]),0.,atol=1e-8)
