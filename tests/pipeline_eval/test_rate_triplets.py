import gzip
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km
from tools.pipeline_eval.qualification.rate_triplet_trials import MODES, OUTPUT, ROSTER
from tools.pipeline_eval.variants import rate_triplets as method


def raw_capture(values):
    probes = [
        dict(
            receiver_id=0,
            channel=1,
            actual_rf_hz=11.3e9,
            valid_start_counter=1000 + 350 * i,
            candidates=[
                dict(
                    candidate_rank=0,
                    fractional_tracking_cfo_hz=method.wrap(f),
                    fractional_margin=0.3,
                    passed_fractional_margin_gate=True,
                )
            ],
        )
        for i, f in enumerate(values)
    ]
    return SimpleNamespace(probes=probes, first_counter=1000, sample_rate_hz=1000, probe_ms=20)


def test_triplets_recover_planted_lane_across_a_cfo_wrap():
    rng = np.random.default_rng(1005)
    t = 0.35 * np.arange(96)
    f = 107000 + 965 * t - 12 * (t - 16) ** 2 + 0.18 * (t - 16) ** 3
    capture = raw_capture(f + rng.normal(0, 14, len(t)))
    segments = method.tracklets(capture)
    assert len(segments) == 1
    segment = segments[0]
    assert segment.points >= len(t) - 1
    error = segment.frequency - np.interp(segment.times - 0.01, t, f)
    assert np.max(abs(error - np.mean(error))) < 15


def test_random_candidates_withhold_before_opening_the_catalogue():
    rng = np.random.default_rng(8758)
    capture = raw_capture(rng.uniform(-110_000, 110_000, 515))
    outcome = method.run(capture)
    assert outcome["status"] == "withheld"
    assert outcome["metrics"]["tracks"] == 0
    assert all(a["latlon"] is None and a["forced_latlon"] is None for a in outcome["arms"].values())


def circular_orbit_sky():
    rng = np.random.default_rng(8951)
    site = [23.4, 143.2]
    receiver = geodetic_to_ecef_km(*site, 0.0)
    east, north, up = ecef_to_enu_matrix(*site)
    n_sat = 8
    radius, velocity = 6871.0, 7.62
    rf = 1e9 * np.tile([11.42, 11.57, 11.68, 11.82], 2)
    positions = np.empty((n_sat, n_sat, 7, 3))
    velocities = np.empty_like(positions)
    observed = np.empty((n_sat, 7))
    segments = []
    midpoints = np.linspace(38, 240, n_sat)
    theta = np.arange(n_sat) * 2.39996
    cross = east * np.sin(theta[:, None]) + north * np.cos(theta[:, None])
    track = east * np.cos(theta[:, None]) - north * np.sin(theta[:, None])
    angle = np.deg2rad(rng.uniform(0.4, 3.8, n_sat))[:, None]
    initial = radius * (np.cos(angle) * up + np.sin(angle) * cross)
    for i, center in enumerate(midpoints):
        t = center + np.linspace(-19, 19, 7)
        phase = (t[None, :, None] - midpoints[:, None, None]) * velocity / radius
        p = initial[:, None, :]
        tangent = track[:, None, :]
        positions[i] = np.cos(phase) * p + radius * np.sin(phase) * tangent
        velocities[i] = -velocity / radius * np.sin(phase) * p + velocity * np.cos(phase) * tangent
        delta = positions[i, i] - receiver
        rate = np.einsum("ni,ni->n", delta, velocities[i, i]) / np.linalg.norm(delta, axis=1)
        measured = -rf[i] / method.LIGHT_KM_S * rate
        measured += 1500 - 700 * (i >= 4) + 9000 * (rf[i] / 1e9 - 11.5)
        observed[i] = measured
        segments.append(
            method.Segment(0, 1 + i % 4 + 4 * (i >= 4), rf[i], 48, t, measured, 2900, 5.0)
        )
    sky = method.Sky(np.arange(n_sat), rf, observed, positions, velocities)
    return site, sky, segments


def test_tile_consensus_and_shared_calibration_gain_with_planted_physical_orbits():
    site, sky, segments = circular_orbit_sky()
    tile = {"center": method.offset_site(site, 3, -4), "width_km": 25}
    (vote, candidate), _ = method.choose_sites(sky, tile)
    assert method.separation(candidate, site) < 1
    assert vote > 7.9
    selected = method.assignments(sky, segments, candidate)
    assert {i: row[0] for i, row in selected.items()} == dict(enumerate(range(8)))
    zero, fitted = (method.fit(sky, segments, selected, candidate, tile, c) for c in (False, True))
    assert fitted["conditional_rms_hz"] < zero["conditional_rms_hz"]
    assert abs(fitted["fitted_c_hz_per_ghz"] - 9000) < 100
    assert method.separation(site, fitted["forced_latlon"]) < 0.1


def test_null_catalogue_association():
    site, sky, segments = circular_orbit_sky()
    sky.measured *= -1
    assert method.assignments(sky, segments, site) == {}


def test_sealed_capture_trials_bind_both_modes_to_the_same_native_and_causal_input():
    recorded = []
    digest = hashlib.sha256(Path(method.__file__).read_bytes()).hexdigest()
    for mode in MODES:
        with gzip.open(OUTPUT / f"{mode}.jsonl.gz", "rt") as stream:
            rows = list(map(json.loads, stream))
        assert [r["id"] for r in rows] == list(ROSTER)
        for row in rows:
            assert row["mode"] == mode
            assert row["implementation_sha256"] == digest
            assert set(row["result"]["arms"]) == {"c0", "fitted_c"}
            for arm in row["result"]["arms"].values():
                assert "latlon" in arm and "forced_latlon" in arm
        recorded.append(rows)
    for first, second in zip(*recorded, strict=True):
        assert first["input_sha256"] != second["input_sha256"]
        assert first["native_sha256"] == second["native_sha256"]
        assert first["catalog_sha256"] == second["catalog_sha256"]
