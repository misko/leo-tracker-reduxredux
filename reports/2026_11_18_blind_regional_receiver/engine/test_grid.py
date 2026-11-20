"""Offline checks with generated elements and independent SGP4 sample times."""

from datetime import UTC, datetime
from types import SimpleNamespace

import numpy as np
import pytest
from sgp4.api import SatrecArray

from leo.sky.frames import (
    ecef_to_enu_matrix,
    geodetic_to_ecef_km,
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    teme_to_ecef,
)
from leo.sky.propagation import element_line_checksum, parse_element_sets

from .grid import HALF_WIDTH_KM, fit_grid, make_tile, prepare_sky, score_at

_DAY_NS = 86_400 * 10**9
_ANCHOR = int(datetime(2026, 1, 5, tzinfo=UTC).timestamp()) * 10**9


def _tle(number, day, node=122.0, phase=67.0, inclination=87.0, motion=15.1):
    line1 = f"1 {number:05d}U 26001A   26{day:012.8f}  .00000000  00000-0  00000-0 0  999"
    line2 = (
        f"2 {number:05d} {inclination:8.4f} {node:8.4f} 0005000"
        f"   0.0000 {phase:8.4f} {motion:11.8f}    1"
    )
    return "".join(f"{line}{element_line_checksum(line)}\n" for line in (line1, line2))


def _observation():
    return SimpleNamespace(anchor_utc_ns=_ANCHOR, cutoff_utc_ns=_ANCHOR - 10**9,
                           catalog_timestamp_ns=_ANCHOR - _DAY_NS // 4,
                           duration_s=240.0, tracks=())


def test_catalog_rejects_future_snapshot_and_excludes_future_or_stale_elements():
    obs = _observation()
    text = (_tle(100, 4.3) + _tle(101, 5.1) + _tle(100, 4.5)
            + _tle(102, 1.0) + _tle(103, 4.9) + _tle(100, 4.9))
    sky = prepare_sky(obs, text.encode())
    assert sky.stats["catalog_entries"] == 6
    assert sky.stats["causal_satellites"] == sky.stats["coarse_satellites"] == 1
    assert sky.satellites[0].satnum == 100
    assert sky.satellites[0].epochdays == pytest.approx(4.5)
    assert sky.stats["coarse_state_evaluations"] == sky.stats["coarse_knots"]
    obs.catalog_timestamp_ns = _ANCHOR
    with pytest.raises(ValueError, match="after the observation cutoff"):
        prepare_sky(obs, text)


def _direct_states(catalogue, times):
    julian, fraction = julian_day_from_utc_ns(_ANCHOR + np.rint(times * 1e9).astype(np.int64))
    codes, position, velocity = SatrecArray(catalogue.satellites).sgp4(julian, fraction)
    assert not codes.any()
    return teme_to_ecef(position, velocity, greenwich_mean_sidereal_time_rad(julian, fraction))


@pytest.fixture(scope="module")
def dateline_scene():
    rng = np.random.default_rng(550)
    text = "".join(
        _tle(number, 4.45, rng.uniform(0, 360), rng.uniform(0, 360),
             rng.uniform(75, 100), rng.uniform(14.8, 15.8))
        for number in range(1000, 1256)
    )
    catalogue = parse_element_sets(text)
    center = (79.94, 179.95)
    truth = (80.02, -179.86)
    observer = geodetic_to_ecef_km(*truth, 0.0)
    up = ecef_to_enu_matrix(*truth)[2]
    tracks = []
    claimed = set()
    for batch, start in enumerate((0.7, 55.7, 110.7, 165.7)):
        times = np.linspace(start, start + 58.2, 23)
        position, velocity = _direct_states(catalogue, times + 0.15 * (-1)**batch)
        delta = position - observer
        ray = delta / np.linalg.norm(delta, axis=-1)[..., None]
        eligible = np.flatnonzero(((ray @ up) > 0.26).all(axis=1))
        # Group tracks cover independent satellites and a range of elevation histories.
        ranked = sorted(eligible, key=lambda i: (-np.max(ray[i] @ up), i))
        for owner in [i for i in ranked if i not in claimed][:5]:
            claimed.add(owner)
            rf_hz = rng.uniform(10.7e9, 12.4e9)
            doppler = -(rf_hz / 299792.458) * np.sum(ray[owner] * velocity[owner], axis=1)
            tracks.append(dict(times=times, values=doppler + rng.normal(0.0, 30.0, len(times)),
                               rf_hz=rf_hz, receiver=batch % 2 + 1, channel=batch + 1))
    assert len(tracks) >= 8
    sky = prepare_sky(_observation(), text)
    return sky, make_tile(sky, center), tracks, center, truth


def test_refined_doppler_fit_across_date_line_and_matched_rf_offset(dateline_scene):
    sky, tile, tracks, center, truth = dateline_scene
    assert 0 < tile.stats["fine_satellites"] < sky.stats["coarse_satellites"]
    first = fit_grid(tile, tracks)
    assert first is not None
    assert first["n_tracks"] == len(tracks)
    assert first["score"] > 0.97
    assert first["rms_hz"] < 65
    expected_xy = ecef_to_enu_matrix(*center)[:2] @ (
        geodetic_to_ecef_km(*truth, 0.0) - geodetic_to_ecef_km(*center, 0.0)
    )
    assert np.linalg.norm(np.asarray(first["xy"]) - expected_xy) < 0.75
    assert first["latlon"][0] == pytest.approx(truth[0], abs=0.004)
    assert first["latlon"][1] == pytest.approx(truth[1], abs=0.035)

    injected = []
    for i, track in enumerate(tracks):
        bump = 28_000.0 * (track["rf_hz"] / 1e9 - 11.5) + (i % 5 - 2) / 4.4e-6
        injected.append(dict(track, values=track["values"] + bump))
    second = fit_grid(tile, injected)
    assert second["xy"] == first["xy"]
    assert second["n_tracks"] == first["n_tracks"]
    assert second["score"] == pytest.approx(first["score"], abs=1e-11)
    assert second["rms_hz"] == pytest.approx(first["rms_hz"], abs=1e-9)


def test_fixed_score_uses_same_metric_and_counts_missing_tracks(dateline_scene):
    _, tile, tracks, _, _ = dateline_scene
    best = fit_grid(tile, tracks)
    exact = score_at(tile, tracks, best["xy"])
    for field, value in exact.items():
        assert value == pytest.approx(best[field])
    missing = dict(tracks[0], times=tracks[0]["times"] + 900.0)
    with_missing = score_at(tile, [*tracks, missing], best["xy"])
    assert with_missing["score"] == pytest.approx(exact["score"] * len(tracks) / (len(tracks) + 1))
    assert with_missing["rms_hz"] == exact["rms_hz"]
    assert with_missing["n_tracks"] == exact["n_tracks"]
    assert fit_grid(tile, tracks[:3]) is None
    with pytest.raises(ValueError, match="inside this tile"):
        score_at(tile, tracks, [HALF_WIDTH_KM + 0.1, 0.0])


def test_empty_causal_sky_at_pole_declines_fit():
    sky = prepare_sky(_observation(), _tle(101, 5.1))
    tile = make_tile(sky, (90.0, 179.0))
    assert tile.stats["fine_satellites"] == 0
    assert fit_grid(tile, []) is None
    assert score_at(tile, [], (0.0, HALF_WIDTH_KM)) == dict(score=None, n_tracks=0, rms_hz=None)
    track = dict(times=[0.0, 10.0, 15.0, 20.0], values=[500.0, 1000.0, 2500.0, 4700.0],
                 rf_hz=11.4e9)
    assert score_at(tile, [track], (0.0, HALF_WIDTH_KM)) == dict(score=0.0, n_tracks=0, rms_hz=None)
