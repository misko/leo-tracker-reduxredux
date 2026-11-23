import pytest

from reports.ALGO08.v3.short_shared_prep import count_reuse, lane_keys


def test_keeps_exact_coarse_frequency_bits_and_original_wrap_fallback():
    seeds = [{"epoch": 3, "hz": 500.}, {"epoch": 128, "hz": -0.},
             {"epoch": 129, "hz": -0.}, {"epoch": 13328, "hz": 0.}]
    keys = lane_keys(seeds)
    assert len(keys) == 2
    assert all(x == 0 for x in keys.values())
    assert lane_keys([{"epoch": 13329, "hz": -625.}]) == {}
    with pytest.raises(ValueError, match="four-request"):
        lane_keys(seeds + [seeds[0]])


def test_reuses_bits_across_lanes_but_respects_each_pilot_and_lru_capacity():
    a = lane_keys([{"epoch": 99, "hz": -625.}])
    b = lane_keys([{"epoch": 99, "hz": 625.}])
    rows = [("lower", a), ("upper", a), ("lower", b), ("lower", a), ("upper", a)]
    assert count_reuse(rows, 1) == {"hits": 1, "misses": 4, "keys": 5}
    assert count_reuse(rows, None) == {"hits": 2, "misses": 3, "keys": 5}
