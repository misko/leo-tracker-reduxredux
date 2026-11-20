import gzip
import json
from types import SimpleNamespace

import numpy as np

from tools.pipeline_eval.qualification.pass_geometry_trials import (
    MODES,
    OUTPUT,
    ROSTER,
    bound_source,
)
from tools.pipeline_eval.variants import pass_geometry as method
from tools.pipeline_eval.variants import rate_triplets as rate


def test_rate_plane_and_acceleration_recover_both_earth_intersections():
    radius = rate.EARTH_KM
    position = np.array([[6870.0, 0.0, 0.0]])
    velocity = np.array([[0.0, 7.5, 0.0]])
    acceleration = np.array([[-0.008, 0.0, 0.0]])
    angle = 0.053
    planted = radius * np.array([np.cos(angle), 0, np.sin(angle)])
    delta = position[0] - planted
    target = (np.sum(velocity**2) + delta @ acceleration[0]) / np.linalg.norm(delta)
    for side in (-1, 1):
        result, valid = method.intersect_pass(position, velocity, acceleration, target, side)
        assert valid.tolist() == [True]
        np.testing.assert_allclose(result[0], planted * [1, 1, -side], atol=0.006)
        assert abs((position[0] - result[0]) @ velocity[0]) < 1e-9
    _, valid = method.intersect_pass(position, velocity, acceleration, 1.0, -1)
    assert valid.tolist() == [False]


def test_straight_pass_fit_recovers_closest_approach_outside_the_observed_track():
    rng = np.random.default_rng(73241)
    times = np.linspace(90, 130, 7)
    amplitude = method.SPEED_KM_S * 11.45e9 / rate.LIGHT_KM_S
    elapsed = times - 144
    frequency = 91_000 - amplitude * elapsed / np.hypot(elapsed, 84)
    frequency += rng.normal(0, 14, size=len(times))
    segment = rate.Segment(0, 1, 11.45e9, 55, times, frequency, 200, 20)
    inferred = method.fit_pass(segment, 0)
    assert abs(inferred.time_s - 144) < 1
    assert abs(inferred.slope_hz_s - amplitude / 84) < 25
    assert inferred.residual_hz < 20


def test_group_coherence_picks_planted_orbits_with_worse_individual_shape_scores():
    count = 6
    rng = np.random.default_rng(8452)
    source = SimpleNamespace(
        evaluate=lambda _site, *, detail: (
            np.tile(np.arange(count), 2),
            np.arange(2 * count),
            np.r_[np.repeat(100.0, count), np.repeat(10.0, count)],
            np.r_[900 + rng.normal(0, 40, count), np.linspace(-99_000, 99_000, count)],
        )
    )
    segments = [SimpleNamespace(group=0) for _ in range(count)]
    merit, labels = method.coherent(source, segments, [0, 0])
    assert merit > 6
    assert {k: value[0] for k, value in labels.items()} == dict(enumerate(range(count)))


def test_random_candidates_withhold_without_requesting_an_orbit_archive():
    rng = np.random.default_rng(90613)
    probes = [
        dict(
            receiver_id=0,
            channel=1,
            actual_rf_hz=11.45e9,
            valid_start_counter=i * 350,
            candidates=[
                dict(
                    candidate_rank=0,
                    fractional_tracking_cfo_hz=float(value),
                    fractional_margin=0.41,
                    passed_fractional_margin_gate=True,
                )
            ],
        )
        for i, value in enumerate(rng.uniform(-110_000, 110_000, 412))
    ]
    capture = SimpleNamespace(probes=probes, first_counter=0, sample_rate_hz=1000, probe_ms=20)
    result = method.run(capture)
    assert result["status"] == "withheld"
    assert result["metrics"]["estimated_passes"] == 0
    assert all(a["forced_latlon"] is None for a in result["arms"].values())


def test_sealed_roof_positions_cover_both_modes_at_the_locked_inputs():
    assert json.loads((OUTPUT / "roof-source-lock.json").read_bytes()) == bound_source()
    versions = []
    for mode in MODES:
        with gzip.open(OUTPUT / f"{mode}.jsonl.gz", "rt") as stream:
            rows = list(map(json.loads, stream))
        assert [r["id"] for r in rows] == list(ROSTER)
        assert all(r["mode"] == mode and r["method"] == method.METHOD for r in rows)
        assert all(set(r["result"]["arms"]) == set(rate.ARMS) for r in rows)
        versions.append([(r["native_sha256"], r["catalog_sha256"]) for r in rows])
    assert versions[0] == versions[1]
