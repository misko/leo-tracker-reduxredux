import math

from tools.pipeline_eval.variants.experimental.receiver_brackets import (
    REFINE,
    Measurement,
    coverage,
    interpolate,
    support_count,
)
from tools.pipeline_eval.variants.experimental.receiver_tracking import ADC, PERIOD, TICKS_PER_FRAME


def factor(counter, epoch_ticks, hz, rank=0):
    relative = ((epoch_ticks - (3 * counter) % TICKS_PER_FRAME) % TICKS_PER_FRAME) / 3
    integer = round(relative) % PERIOD
    return rank, integer, math.remainder(relative - integer, PERIOD), hz, .09, .02


def test_interpolates_wrapped_phase_and_signed_cfo_with_reversed_neighbor_ranks():
    left = 8_192_000_000_000_701
    middle = left + 5_000_000
    right = left + 15_000_000
    anchors = (
        Measurement("left", left, 0, (factor(left, 39970, -315_000),
                                      factor(left, 6800, 251_000, 1)), 6),
        Measurement("right", right, 0, (factor(right, 6830, 248_000),
                                        factor(right, 90, -312_000, 1)), 6),
    )
    actual = (factor(middle, 10, -314_000), factor(middle, 6810, 250_000, 1))
    reason, hints = interpolate(*anchors, counter=middle, center=0)
    assert reason == "proposed"
    assert [hz for _, hz in hints] == [-314_000, 250_000]
    assert support_count(actual, hints, REFINE) == len(actual)


def test_count_mismatch_ambiguity_and_transient_discovery_are_explicit():
    left, middle, right = ADC, 2 * ADC, 3 * ADC
    first = Measurement("left", left, 0, (factor(left, 100, -300_000),), 7)
    last = Measurement("right", right, 0, (factor(right, 100, -300_000),), 7)
    only_middle = factor(middle, 1500, 220_000, 1)
    current = Measurement("middle", middle, 0, (factor(middle, 100, -300_000), only_middle), 9)
    result = coverage({("capture", 0): [first, current, last]})
    assert result["counts"]["middle_only_factors"] == 1
    assert result["counts"]["other_factors_in_middle"] == 1
    assert result["counts"]["outer_whole_lane"] == 0
    assert result["counts"]["outer_factors"] == 1

    last.factors = ()
    assert interpolate(first, last, counter=middle, center=0) == ("different_anchor_counts", ())
    close = -299_800
    first.factors += (factor(left, 103, close, 1),)
    last.factors = (factor(right, 100, -300_000), factor(right, 103, close, 1))
    assert interpolate(first, last, counter=middle, center=0) == ("ambiguous_links", ())
