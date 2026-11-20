import json

import numpy as np
import pytest
from sgp4.api import WGS72, Satrec

from tools.pipeline_eval.qualification.prefix_reuse_cache import EphemerisReuse
from tools.pipeline_eval.qualification.prefix_reuse_worker import RATE, NativeIncrements
from tools.pipeline_eval.reference import grid


def setup():
    return {
        "request": {"mode": "native", "cutoff": 10, "catalog_timestamp": 9, "probe_limit": 12},
        "anchor": {
            "sample_counter": 0,
            "before": {"realtime_ns": 10},
            "after": {"realtime_ns": 12},
        },
    }


def visit(rx, second):
    return dict(
        receiver_id=rx,
        channel=1,
        actual_rf_hz=11e9,
        valid_start_counter=second * RATE,
        candidates=[
            dict(
                passed_fractional_margin_gate=True,
                fractional_margin=2.0,
                candidate_rank=1,
                fractional_tracking_cfo_hz=30.0,
            ),
        ],
    )


def event(cutoff, last, previous, visits):
    return dict(
        checkpoint=cutoff,
        last_sample_counter=last,
        previous_probes=previous,
        expected_probes=previous + len(visits),
        probes=visits,
    )


def test_increment_causality_and_retry():
    stream = NativeIncrements(setup())
    first = event(120, 119 * RATE, 0, [visit(0, 100), visit(1, 100)])
    stream.add(first, 356)
    second = event(180, 179 * RATE, 2, [visit(0, 179), visit(1, 175)])
    with pytest.raises(ValueError):
        stream.add(second, 352)
    assert (stream.probes, stream.frontier, stream.index) == (2, 119 * RATE, 1)
    second["probes"][0] = visit(0, 174)
    stream.add(second, 350)
    clock, lanes, counts = stream.peak_lanes(None, 12, 10)
    assert clock == {"anchor_utc_ns": 11, "cutoff_utc_ns": 10, "duration_s": 179}
    assert lanes[11e9, 1, 1] == [(100.01, 30.0), (174.01, 30.0)]
    assert counts == {"native_bytes": 706, "probes": 4, "winning_peaks": 4}
    with pytest.raises(ValueError):
        stream.add(second, 350)


def test_knot_growth_subsets_and_exact_fallback():
    satellites = []
    for i in range(3):
        sat = Satrec()
        sat.sgp4init(WGS72, "i", 1000 + i, 27_300, 0, 0, 0, 0.001, 0.5, 0.9, 0, 0.064, i)
        satellites.append(sat)
    anchor = 1_700_000_000_000_000_000
    cache = EphemerisReuse(grid)
    for duration, step, active in (
        (120, grid.COARSE_ORBIT_STEP_S, satellites),
        (180, grid.COARSE_ORBIT_STEP_S, satellites[::-1]),
        (120, grid.FINE_ORBIT_STEP_S, satellites[:1]),
        (180, grid.FINE_ORBIT_STEP_S, satellites[1:]),
        (120, grid.COARSE_ORBIT_STEP_S, satellites[:1]),
        (120, 3, satellites),
    ):
        knots = grid._knots(duration, step)
        actual = cache(active, anchor, knots)
        expected = grid._valid_states(active, anchor, knots)
        assert actual[0] == expected[0]
        for candidate, stock in zip(actual[1:], expected[1:], strict=True):
            np.testing.assert_array_equal(candidate, stock)
    stats = cache.sums()
    assert 0 < stats["cells"] < stats["requested_cells"]
    assert stats["exact_fallbacks"] == 1
    json.dumps(stats, allow_nan=False)
