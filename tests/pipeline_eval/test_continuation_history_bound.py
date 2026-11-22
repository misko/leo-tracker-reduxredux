from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

from tools.pipeline_eval.variants.carrier_continuation import votes
from tools.pipeline_eval.variants.experimental.continuation_history_bound import (
    history_allows_three,
)
from tools.pipeline_eval.variants.experimental.deferred_continuation import Visit

NOW = 2**62 + 4_200_000


def donors(rows):
    return [Visit(NOW - age, None, frequencies) for age, frequencies in rows]


@pytest.mark.parametrize("rows,possible", [
    ([(30_000_000, (0,)), (20_000_000, (6000,)), (10_000_000, (0,))], False),
    ([(30_000_000, (0, 0)), (20_000_000, (0,)), (10_000_000, (90_000,))], False),
    ([(30_000_000, (50_000, 0)), (20_000_000, (-50_000, 0)), (10_000_000, (0,))], True),
    ([(4_000_000, None), (3_000_000, (0,)), (2_000_000, (0,))], True),
    ([(7_000_000, (90_000,)), (3_000_000, (0,)), (2_000_000, (0,)), (1, None)], False),
    ([(7_000_000, (0,)), (3_000_000, (90_000,)), (2_000_000, (0,)), (1, None)], True),
    ([(4_000_000, (0,)), (3_000_000, None), (2_000_000, None)], True),
    ([(4_000_000, None), (3_000_000, None), (2_000_000, None)], True),
    ([(3_999_999, None), (3_000_000, None), (2_000_000, None)], False),
    ([(4_000_000, None), (3_000_000, None)], False),
    ([(30_000_000, (float("inf"),)), (20_000_000, (6000,)), (10_000_000, (0,))], True),
])
def test_distinct_donors_with_zero_to_three_unknowns_and_a_span(rows, possible):
    assert history_allows_three(donors(rows), NOW) == possible


@pytest.mark.parametrize("cfo_sign", [-1, 1])
@pytest.mark.parametrize("slope", [-8000, 8000])
@pytest.mark.parametrize("ages", [(80_000_000, 4_000_000, 1), (80_000_000, 4_000_001, 4_000_000)])
def test_float_enclosure_retains_actual_votes_at_the_slope_and_hz_bounds(cfo_sign, slope, ages):
    hz = cfo_sign * (2**30 - 100_000)
    residuals = (0, 800, -800)
    frequencies = tuple(hz - slope * (age / 1e7) + residual
                        for age, residual in zip(ages, residuals, strict=True))
    stock = [(NOW - age, (value,)) for age, value in zip(ages, frequencies, strict=True)]
    assert votes(hz, stock, NOW) == 3
    for mask in range(8):
        history = [Visit(counter, None, None if mask & (1 << i) else values)
                   for i, (counter, values) in enumerate(stock)]
        assert history_allows_three(history, NOW)


def test_deferred_visit_can_still_be_queried_as_a_later_donor():
    reports = Path(__file__).resolve().parents[2] / "reports/ALGO08/single-core-2x"
    source = reports / "deferred_history_bound_trial.py"
    spec = spec_from_file_location(source.stem, source)
    trial = module_from_spec(spec)
    spec.loader.exec_module(trial)
    planner = trial.planner_with_bound()(64)
    lane = (0, 3, 0)
    planner.lanes[lane].extend(donors(
        [(30_000_000, (0,)), (20_000_000, (6000,)), (10_000_000, (0,))],
    ))
    measured = []
    factor = dict(fractional_tracking_cfo_hz=0., fractional_margin=.2, candidate_rank=0)

    def probe(counter):
        return dict(receiver_id=lane[0], channel=lane[1], actual_rf_hz=lane[2],
                    valid_start_counter=counter)

    def measure(counter):
        measured.append(counter)
        return [factor]

    later = NOW + 10_000_000
    assert planner.select(probe(NOW), lambda: measure(NOW)) == []
    assert measured == []
    assert planner.counts["ruled_out_before_native"] == 1
    assert planner.select(probe(later), lambda: measure(later)) == [factor]
    assert measured == [later, NOW]
