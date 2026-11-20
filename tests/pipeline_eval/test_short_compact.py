from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.qualification import short_compact as trial
from tools.pipeline_eval.qualification import short_compact_release as release
from tools.pipeline_eval.qualification.short_compact_worker import geometry
from tools.pipeline_eval.scoring import ARMS


def document():
    spans = (0, 7499, 7503, 8000, 15001)
    clock = [dict(monotonic_ns=start * 10_000_000, realtime_ns=0) for start in spans]
    return dict(
        clock_anchor=dict(sample_counter=10, before=clock[0], after=clock[0]),
        last_sample_counter=span_end(spans[-1]),
        delivery_clocks=clock,
        source=dict(
            sample_rate_hz=100,
            probe_ms=20,
            session_id="fixture",
            probes=[
                dict(visit_index=i, receiver_id=rx, valid_start_counter=10 + start, candidates=[])
                for i, start in enumerate(spans)
                for rx in (0, 1)
                if i != 3
            ],
        ),
        provenance=dict(
            window_count=5,
            processed_windows=4,
            invalid_capture=1,
            excluded_windows=[dict(visit=3, sample_start=8010, sample_end=8012)],
        ),
    )


def span_end(relative):
    return 10 + relative + 2


def test_factor_blocks_preserve_counters_clocks_and_exclude_crossings():
    original = document()
    windows = trial.scopes(original)
    first, audit = trial.snapshot(original, windows, (0, 75))
    second, support = trial.snapshot(original, windows, (75, 150))
    assert (audit["first_visit"], audit["last_visit"]) == (0, 0)
    assert (support["first_visit"], support["last_visit"]) == (2, 3)
    assert support["invalid"] == 1
    assert second["clock_anchor"] == original["clock_anchor"]
    assert second["last_sample_counter"] == 8012
    assert second["source"]["probes"][0]["valid_start_counter"] == 7513
    future_poisoned = deepcopy(original)
    future_poisoned["source"]["probes"][-1]["candidates"] = [{"future_outcome": True}]
    assert trial.snapshot(future_poisoned, trial.scopes(future_poisoned), (0, 75))[0] == first


def block(i, *, point=(0.0, 0.0), radius=0.3, wall=20.0):
    point = list(point)
    confidence = dict(
        latlon=point,
        orbits=[1, 2, 3],
        active_points=36,
        nominal_radius95_km=radius,
        information_condition=3.0,
    )
    return dict(
        id="test",
        native_sha256="abc",
        catalog_sha256="def",
        name=str(i),
        tile=dict(center=[0, 0], width_km=25),
        worker_wall_s=wall,
        worker_cpu_s=wall,
        input_preparation_wall_s=0.1,
        support=dict(
            seconds=[i * 75, i * 75 + 74.99],
            first_visit=i * 10,
            last_visit=i * 10 + 9,
            available_s=[(i + 1) * 75, (i + 1) * 75],
        ),
        result=dict(
            status="ok",
            metrics=dict(terminal_local_geometry={arm: dict(confidence) for arm in ARMS}),
            arms={arm: dict(latlon=list(point)) for arm in ARMS},
        ),
    )


def test_two_disjoint_blocks_release_later_both_arm_fix_and_skip_future_work():
    cases = [block(0), block(1, point=(0.001, 0)), block(2, wall=1000)]
    declared, receipt = release.decide(cases)
    assert receipt["released"]
    assert receipt["run_blocks"] == 2
    assert receipt["last_worker_end_elapsed_s"][0] == pytest.approx(170.1)
    assert declared["arms"] == cases[1]["result"]["arms"]
    assert receipt["speculative_cpu_s"] == pytest.approx(40)


def test_gate_rejects_weak_arm_crossing_tile_and_overlapping_ownership():
    cases = [block(i, point=(0.1115, 0), radius=0.4) for i in range(3)]
    cases[1]["result"]["metrics"]["terminal_local_geometry"]["fitted_c"]["orbits"] = [1, 2]
    declared, receipt = release.decide(cases)
    assert declared["status"] == "withheld"
    checks = receipt["checks"][0]["arms"]
    assert "tile_face" in checks["c0"]["earlier_reasons"]
    assert "orbital_support" in checks["fitted_c"]["later_reasons"]
    cases[1]["support"]["first_visit"] = 9
    with pytest.raises(ValueError, match="nonintersecting"):
        release.decide(cases)


def test_conditioning_uses_the_weaker_coordinate_and_only_passing_orbits():
    fixture = SimpleNamespace(
        upper=np.asarray([10.0, 10.0]),
        residual=lambda x: np.asarray([2 * x[0], 4 * x[1]]),
    )
    gates = dict(
        tracks=[
            dict(compatible=True, points=20, norad=12),
            dict(compatible=False, points=70, norad=34),
        ]
    )
    receipt = geometry(fixture, [0.0, 0.0], gates)
    assert receipt["orbits"] == [12]
    assert receipt["information_condition"] == pytest.approx(4)
    assert receipt["nominal_radius95_km"] == pytest.approx(np.sqrt(5.991464547107979 / 4))
