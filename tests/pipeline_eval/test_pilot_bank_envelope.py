import pytest

from reports.ALGO08.v3.pilot_bank_envelope import census, convolution, partition_by_outcome, price


def scan(*pairs):
    return {"seeds": [dict(epoch=e, hz=f) for e, f in pairs]}


def test_census_preserves_exact_cfo_bits_and_scope():
    lanes = [{"scans": [scan((0, -0.), (0, 0.), (8, 0.), (13332, 3.)),
                         scan((0, -0.), (0, -0.), (0, -0.))]}]
    assert census(lanes) == dict(scouts=2, seeds=7, repeated_epoch=3, repeated_cfo=3, repeated_request=2,
                                 close_distinct_epoch_pairs=2, wrap_seeds=6, max_same_epoch=3)


def test_correlation_requires_full_support_and_counts_shared_fft():
    with pytest.raises(ValueError, match="geometry"):
        convolution(352, 9, 359)
    base = convolution(352, 9, 360)
    shared = convolution(352, 9, 360, input_reuse=63/592)
    assert base["minimum_circular_length"] == 360
    assert shared["direct_real_ops"] == 25_344
    assert 1 < shared["fft_over_direct"] < base["fft_over_direct"]
    assert shared["input_reuse_to_equal_direct"] > 63 / 592
    assert convolution(44, 5, 48, direct_ops_per_tap=14)["direct_real_ops"] == 3080


def test_clock_strata_use_recorded_outcome_mix_without_nested_stages():
    rows = {"confirmed": {"stage": {"stages": [1200, 100, 800]}},
            "empty": {"stage": {"stages": [1100, 0, 0]}}}
    assert partition_by_outcome(rows, 2, 8) == {"scout": 9000/1e9, "verify_load": 200/1e9, "verify": 1600/1e9}
    assert price(2., 3.49)["required_stage_speedup"] is None
    assert price(5., 3.49)["fraction_to_save"] == pytest.approx(.698)
