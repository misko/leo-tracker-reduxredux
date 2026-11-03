import importlib.util
from pathlib import Path

import numpy as np

spec = importlib.util.spec_from_file_location('review_analyze', Path(__file__).with_name('analyze.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_error_direction_distance_and_dateline():
    one_degree = module.EARTH_M * np.pi / 180
    np.testing.assert_allclose(module.error_vector(0, 1, 0, 0), [one_degree, 0], atol=1e-8)
    np.testing.assert_allclose(module.error_vector(1, 0, 0, 0), [0, one_degree], atol=1e-8)
    np.testing.assert_allclose(module.error_vector(0, -179, 0, 179), [2*one_degree, 0], atol=1e-8)
    np.testing.assert_array_equal(module.error_vector(37, -122, 37, -122), [0, 0])


def test_mean_preserves_bias_and_cancels_opposite_errors():
    rows = [dict(error_east_m=e, error_north_m=200, posterior_rms_hz=100,
                 converged=True, boundary=False, coefficient_hz_per_ghz=0) for e in (-100, 100)]
    result = module.position_stats(rows)
    assert result['static_equal_weight_mean_error_m'] == 200
    assert result['error_m']['median'] > 200


def test_forward_inverse_coordinates_round_trip():
    for point in ([0,0],[-87,-81],[160,180]):
        lat,lon = module.coordinates(*point)
        np.testing.assert_allclose(module.error_vector(lat,lon,38.5816,-121.4944),
                                   np.array(point)*1000,atol=1e-7)
