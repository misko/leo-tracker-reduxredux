import json
from importlib import import_module
from types import SimpleNamespace

import numpy as np
import pytest

receiver = import_module("reports.2026_11_18_blind_regional_receiver.engine.receiver")
grid = receiver.grid


def track(start, channel, width=12):
    return dict(
        times=np.linspace(start, start + width, 6).tolist(),
        values=[0, 300, 580, 820, 1050, 1220],
        rf_hz=10.7e9 + channel * 0.01e9,
        receiver=1,
        channel=channel,
    )


def observation(tracks):
    return dict(
        duration_s=100, tracks=tracks, anchor_utc_ns=1, cutoff_utc_ns=1, catalog_timestamp_ns=1
    )


REGIONS = [dict(id="a", center=[10, 10]), dict(id="z", center=[-10, 10])]


@pytest.fixture
def tracks():
    return [track(start, i) for i, start in enumerate((1, 3, 5, 7, 54, 62, 69, 75, 42))]


def fake_grid(
    monkeypatch,
    tracks,
    holds=(0.91, 0.4),
    nulls=(0.45, 0.62),
    early_xy=(2, 1),
    late_xy=(3, 0),
    pooled_xy=(2, 0),
):
    calls = dict(fits=[], scores=[])
    original = {t["channel"]: tuple(t["times"]) for t in tracks}

    def fit(tile, subset):
        assert len(subset) >= 4
        is_early = all(t["times"][-1] <= 50 for t in subset)
        is_late = all(t["times"][0] >= 50 for t in subset)
        kind = "early" if is_early else "late" if is_late else "pooled"
        xy = {"early": early_xy, "late": late_xy, "pooled": pooled_xy}[kind]
        calls["fits"].append((tile.center, kind, tuple(t["channel"] for t in subset)))
        return dict(
            xy=xy,
            latlon=[tile.center[0] + xy[1] / 111, tile.center[1] + xy[0] / 111],
            score=0.93,
            n_tracks=len(subset),
            rms_hz=63.0,
        )

    def score(tile, subset, xy):
        assert xy == early_xy
        is_original = all(t["times"] == original[t["channel"]] for t in subset)
        value = (holds if is_original else nulls)[int(tile.center[0] < 0)]
        calls["scores"].append((tile.center, is_original, subset))
        return dict(score=value, n_tracks=len(subset), rms_hz=72.0)

    monkeypatch.setattr(grid, "prepare_sky", lambda *_: SimpleNamespace(stats={}))
    monkeypatch.setattr(
        grid, "make_tile", lambda _, center: SimpleNamespace(center=center, stats={})
    )
    monkeypatch.setattr(grid, "fit_grid", fit)
    monkeypatch.setattr(grid, "score_at", score)
    return calls


def deterministic(result):
    diagnostics = {
        k: v for k, v in result["diagnostics"].items() if k not in ("wall_s", "stage_seconds")
    }
    return dict(result, diagnostics=diagnostics)


def test_fixed_nominees_and_set_wide_changed_time(monkeypatch, tracks):
    calls = fake_grid(monkeypatch, tracks)
    result = receiver.solve(observation(tracks), REGIONS, "synthetic")
    assert result["status"] == "fix"
    assert result["region_id"] == result["best_region"] == "a"
    assert result["latlon"] == result["best_latlon"] == [10.0, 10.0 + 2 / 111]
    assert result["diagnostics"]["region_result"] == dict(
        status="accepted", region_id="a", reason="accepted"
    )
    assert result["diagnostics"]["work"] == dict(
        tiles=2, grid_fits=4, point_scores=40, null_schedules=19
    )
    assert result["diagnostics"]["held_evidence"]["null_maxima"] == [0.62] * 19
    observed = {t["channel"]: t for t in tracks}
    schedules = set()
    for region, is_original, subset in calls["scores"]:
        assert {t["channel"] for t in subset} == {4, 5, 6, 7}
        if not is_original and region[0] == 10:
            schedules.add(tuple(t["times"][0] for t in subset))
        for shifted in subset:
            original = observed[shifted["channel"]]
            assert shifted["values"] == tuple(original["values"])
            assert shifted["times"][0] >= 50 and shifted["times"][-1] <= 100
            assert np.diff(shifted["times"]) == pytest.approx(np.diff(original["times"]))
            assert (shifted["times"][0] == original["times"][0]) == is_original
    assert len(schedules) == 19
    fits_by_kind = {kind: set(channels) for _, kind, channels in calls["fits"]}
    assert fits_by_kind == {"early": {0, 1, 2, 3}, "late": {4, 5, 6, 7}, "pooled": set(range(9))}
    assert json.loads(json.dumps(result, allow_nan=False)) == result


def test_other_regions_can_veto_top_observed_region(monkeypatch, tracks):
    fake_grid(monkeypatch, tracks, nulls=(0.45, 0.90))
    result = receiver.solve(observation(tracks), REGIONS, "synthetic")
    assert result["status"] == "withheld"
    assert result["reason"] == "failed_changed_time_controls"
    assert result["region_id"] is result["latlon"] is None
    assert result["best_region"] == "a" and result["best_latlon"] is not None
    assert result["diagnostics"]["held_evidence"]["null_exceedances"] == 0


@pytest.mark.parametrize(
    ("late_xy", "pooled_xy", "reason"),
    [
        ((10, 0), (5, 0), "inconsistent_position"),
        ((2, 1), (8, 1), "inconsistent_position"),
        ((11, 0), (12, 0), "inconsistent_position"),
    ],
)
def test_region_only_survives_precise_disagreement(monkeypatch, tracks, late_xy, pooled_xy, reason):
    fake_grid(monkeypatch, tracks, late_xy=late_xy, pooled_xy=pooled_xy)
    result = receiver.solve(observation(tracks), REGIONS, "synthetic")
    assert result["status"] == "withheld" and result["reason"] == reason
    assert result["diagnostics"]["region_result"]["region_id"] == "a"
    assert result["latlon"] is None
    assert result["best_latlon"] == [10 + pooled_xy[1] / 111, 10 + pooled_xy[0] / 111]


def test_compatible_edge_position_is_withheld(monkeypatch, tracks):
    fake_grid(monkeypatch, tracks, early_xy=(11, 1), late_xy=(11, 0), pooled_xy=(12, 0))
    result = receiver.solve(observation(tracks), REGIONS, "synthetic")
    assert result["reason"] == "position_at_tile_boundary"
    assert result["diagnostics"]["position_evidence"]["pooled_boundary_clearance_km"] == 0.5


def test_ties_are_ambiguous_without_order_or_label_preference(monkeypatch, tracks):
    fake_grid(monkeypatch, tracks, holds=(0.91, 0.91))
    first = receiver.solve(observation(tracks), REGIONS, "synthetic")
    reversed_inputs = receiver.solve(observation(tracks[::-1]), REGIONS[::-1], "synthetic")
    renamed_regions = [
        dict(r, id=other["id"]) for r, other in zip(REGIONS, REGIONS[::-1], strict=True)
    ]
    renamed = receiver.solve(observation(tracks), renamed_regions, "synthetic")
    assert deterministic(first) == deterministic(reversed_inputs)
    assert first["reason"] == "ambiguous_region"
    assert first["diagnostics"]["tied_region_ids"] == ["a", "z"]
    assert first["best_region"] == "z" and renamed["best_region"] == "a"
    assert first["best_latlon"] == renamed["best_latlon"]

    coincident = [dict(r, center=REGIONS[0]["center"]) for r in REGIONS]
    result = receiver.solve(observation(tracks), coincident, "synthetic")
    assert result["reason"] == "ambiguous_region"
    assert result["best_region"] is None and result["best_latlon"] is not None


def test_insufficient_split_retains_pooled_forced_point(monkeypatch, tracks):
    fake_grid(monkeypatch, tracks)
    result = receiver.solve(observation(tracks[:4] + [tracks[0], tracks[-1]]), REGIONS, "synthetic")
    assert result["reason"] == "insufficient_disjoint_tracks"
    assert result["best_region"] == "z" and result["best_latlon"] is not None
    assert result["diagnostics"]["forced_source"] == "pooled_only"
    assert result["diagnostics"]["track_counts"] == dict(
        received=6, screened=5, early=4, late=0, pooled=5
    )
    assert receiver.solve(observation([]), REGIONS, "synthetic")["reason"] == "insufficient_tracks"


def test_fewer_than_four_movable_held_tracks_do_not_verify(monkeypatch, tracks):
    tracks = tracks[:4] + [track(50, i, width=50) for i in range(4, 8)]
    fake_grid(monkeypatch, tracks)
    result = receiver.solve(observation(tracks), REGIONS, "synthetic")
    assert result["reason"] == "insufficient_changed_time_controls"
    assert result["diagnostics"]["held_evidence"]["movable_tracks"] == 0


def test_future_catalogue_is_rejected_before_orbit_work(tracks):
    obs = dict(observation(tracks), cutoff_utc_ns=5, catalog_timestamp_ns=6)
    result = receiver.solve(obs, REGIONS, "synthetic")
    assert result["reason"] == "invalid_causal_catalogue"
    assert result["diagnostics"]["work"] == dict(
        tiles=0, grid_fits=0, point_scores=0, null_schedules=0
    )


def test_c0_and_fitted_c_produce_same_scores_and_position(monkeypatch):
    # Analytic ECEF trajectories sampled at the real grid's interpolation knots.
    duration = 240.0
    knots = grid._knots(duration, grid.FINE_ORBIT_STEP_S)
    rng = np.random.default_rng(419)
    starts = np.r_[np.linspace(4, 62, 12), np.linspace(123, 182, 12)]
    rf_hz = np.linspace(10.7e9, 12.7e9, len(starts))
    heading = rng.uniform(0, 2 * np.pi, len(starts))
    origin = np.column_stack((rng.uniform(6860, 7000, len(starts)), np.zeros((len(starts), 2))))
    velocity = 6.5 * np.column_stack((np.zeros(len(starts)), np.sin(heading), np.cos(heading)))
    origin[:, 1:] += rng.uniform(-115, 115, (len(starts), 2))
    closest_seconds = starts + rng.uniform(3, 42, len(starts))
    positions = (
        origin[:, None, :]
        + (knots[None, :] - closest_seconds[:, None])[..., None] * velocity[:, None, :]
    )
    velocities = np.broadcast_to(velocity[:, None, :], positions.shape).copy()

    def make_tile(_, center):
        lat, lon = center
        return grid.Tile(
            grid.geodetic_to_ecef_km(lat, lon, 0),
            grid.ecef_to_enu_matrix(lat, lon),
            duration,
            knots,
            positions,
            velocities,
            {},
        )

    monkeypatch.setattr(grid, "prepare_sky", lambda *_: SimpleNamespace(stats={}))
    monkeypatch.setattr(grid, "make_tile", make_tile)
    planted = [0.025, -0.031]
    site = grid.geodetic_to_ecef_km(*planted, 0)
    plain = []
    for i, start in enumerate(starts):
        times = start + np.linspace(0, 47, 12)
        delta = origin[i] + (times - closest_seconds[i])[:, None] * velocity[i] - site
        radial_velocity = delta @ velocity[i] / np.linalg.norm(delta, axis=1)
        values = -rf_hz[i] * radial_velocity / grid.LIGHT_SPEED_KM_S + (i % 3) * 2000
        plain.append(
            dict(
                times=times.tolist(),
                values=values.tolist(),
                rf_hz=rf_hz[i],
                receiver=i % 3,
                channel=i,
            )
        )

    # Fit the injected level shift on this synthetic fixture alone, then remove it
    # from a copy of the observations while keeping everything else unchanged.
    design = (rf_hz - 11.5e9) / 1e9
    injected_c = 153_000.0
    observed = [
        dict(t, values=(np.asarray(t["values"]) + injected_c * x).tolist())
        for t, x in zip(plain, design, strict=True)
    ]
    level_shift = np.array(
        [np.mean(a["values"]) - np.mean(b["values"]) for a, b in zip(observed, plain, strict=True)]
    )
    fitted_c = design @ level_shift / (design @ design)
    assert fitted_c == pytest.approx(injected_c)
    corrected = [
        dict(t, values=(np.asarray(t["values"]) - fitted_c * x).tolist())
        for t, x in zip(observed, design, strict=True)
    ]
    obs = dict(observation(observed), duration_s=duration)
    regions = [dict(id="signal", center=[0, 0]), dict(id="decoy", center=[3, -2])]
    c0 = receiver.solve(obs, regions, "analytical trajectories")
    fitted = receiver.solve(dict(obs, tracks=corrected), regions, "analytical trajectories")

    for result in (c0, fitted):
        assert result["status"] == "fix", result
        assert result["region_id"] == "signal"
        assert result["latlon"] == pytest.approx(planted, abs=0.004)
    assert c0["latlon"] == fitted["latlon"]
    assert c0["diagnostics"]["work"] == fitted["diagnostics"]["work"]
    for stage in ("early", "late", "pooled"):
        assert c0["diagnostics"]["position_evidence"][stage] == pytest.approx(
            fitted["diagnostics"]["position_evidence"][stage], abs=1e-7
        )
    assert c0["diagnostics"]["held_evidence"]["null_maxima"] == pytest.approx(
        fitted["diagnostics"]["held_evidence"]["null_maxima"], abs=1e-10
    )
    assert c0["diagnostics"]["held_evidence"]["score"] == pytest.approx(
        fitted["diagnostics"]["held_evidence"]["score"], abs=1e-10
    )
