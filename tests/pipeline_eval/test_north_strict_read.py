from reports.ALGO08.v3 import north_strict_read


def test_same_detector_zero_cost_floor_retains_native_and_publication():
    actual = north_strict_read.ceiling(10.5, 5.0, 2.7, 16.0)
    assert actual["zero_cost_floor_s"] == 8.2
    assert actual["same_route_max_ratio"] < 1.6 < actual["against_named_max_ratio"] < 2
    assert actual["required_saving_s"] == 0.5
