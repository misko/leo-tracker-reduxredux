from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.qualification import identity_ablation as trial
from tools.pipeline_eval.qualification.identity_native_export import (
    bind_independent,
    physical_index,
)
from tools.pipeline_eval.scoring import distance_km
from tools.pipeline_eval.variants import fixed_orbit_position as fit


def test_exact_shared_peak_changes_only_identity():
    a = dict(
        observation_id="q",
        candidate_rank=0,
        receiver=0,
        channel=1,
        rf_hz=11e9,
        time_s=18,
        measured_cfo_hz=300,
        epoch_sample=5,
        counter=100,
        norad=100,
    )
    b = dict(a, norad=200)
    c = dict(a, observation_id="r", counter=101)
    d = dict(c, candidate_rank=2)
    rows, counts = trial.stratify([a, c], [b, d])
    assert counts == dict(
        exact_shared_rows=1,
        shared_opportunities_different_rank=1,
        agreeing_labels=0,
        disagreeing_labels=1,
    )
    assert trial._narrow(rows["shared_independent"][0]) == [18, 11e9, 300, 100, 0]
    assert trial._narrow(rows["shared_v5"][0]) == [18, 11e9, 300, 200, 0]
    rows["shared_v5"][0]["residuals"] = {"c0": 42}
    assert "residuals" not in b
    with pytest.raises(ValueError, match="inconsistent"):
        trial.stratify([a], [dict(b, measured_cfo_hz=301)])


def test_export_binds_rank_by_native_fold_and_counts_exact_ties():
    p = dict(
        receiver_id=0,
        visit_index=20,
        valid_start_counter=12_000_000,
        channel=4,
        actual_rf_hz=11e9,
        candidates=[
            dict(
                candidate_rank=2,
                fractional_tracking_cfo_hz=1200,
                fractional_margin=0.5,
                integer_epoch_sample=17,
                fractional_epoch_offset_samples=0.2,
            )
        ],
    )
    cap = SimpleNamespace(
        probes=[p], first_counter=2_000_000, sample_rate_hz=10_000_000, probe_ms=20
    )
    native, _ = physical_index(cap, "scan-verified")
    row = dict(
        receiver=0,
        visit=20,
        channel=4,
        rf_hz=11e9,
        time_s=1.01,
        wrapped_hz=1200,
        orbit=42,
        candidate_column=0,
    )
    samples, count = bind_independent([row], native)
    assert count == 0 and samples[0]["candidate_rank"] == 2 and samples[0]["norad"] == 42
    p["candidates"].append(dict(p["candidates"][0], candidate_rank=3))
    samples, count = bind_independent([dict(row, candidate_column=1)], native)
    assert count == 1 and samples[0]["candidate_rank"] == 3


def geometry_fixture():
    knots = np.arange(-30.0, 160.0, 5.0)
    origin = np.array([[6920, 500, -200], [6980, -200, 100], [6850, 240, 640], [7040, -520, 710]])
    velocity = np.array([[0.0, -6, 4], [1.0, 6, -5], [-1, -3, -6], [0.2, 4, 6]])
    position = origin[:, None] + velocity[:, None] * knots[None, :, None]
    return fit.grid.Tile(
        np.array([6378.137, 0, 0]),
        np.array([[0, 1, 0], [0, 0, 1], [1, 0, 0]]),
        120,
        knots,
        position,
        np.broadcast_to(velocity[:, None], position.shape),
        {},
    )


def test_orbital_phase_and_position_jacobians_match_finite_differences():
    tile = geometry_fixture()
    time = np.linspace(1, 119, 13)
    rf = np.full(len(time), 11e9)
    ids = np.arange(len(time)) % 4
    phase = np.linspace(-14, 14, len(time))
    h = 1e-4
    site = tile.ecef_center_km
    _, xy, dp, _ = fit.geometry(tile, site, time, rf, ids, phase)

    def doppler(view, offset):
        return fit.geometry(tile, view, time, rf, ids, offset)[0]

    np.testing.assert_allclose(
        dp, (doppler(site, phase + h) - doppler(site, phase - h)) / (2 * h), rtol=1e-6, atol=2e-4
    )
    for i, row in enumerate(tile.enu_frame[:2]):
        np.testing.assert_allclose(
            xy[:, i],
            (doppler(site + h * row, phase) - doppler(site - h * row, phase)) / (2 * h),
            rtol=1e-6,
            atol=2e-4,
        )


def test_physical_fit_recovers_planted_geometry_with_real_exact_c0_ablation(monkeypatch):
    tile = geometry_fixture()
    monkeypatch.setattr(fit, "orbit_table", lambda *args: (tile, {i: i for i in range(4)}))
    planted = np.array([[2.2, -3.8]])
    expected = fit.grid._sites(tile, planted)[2][0]
    xyz = fit.grid._sites(tile, planted)[0][0]
    t = np.repeat(np.arange(2, 118), 4)
    orbit = np.tile(np.arange(4), len(t) // 4)
    group = (orbit + t // 4) % 4
    phase = np.array([1.2, -4.5, 7.0, -2.7])[orbit]
    rf = (10.9 + 0.38 * ((orbit + t // 4) % 3)) * 1e9
    f = fit.geometry(tile, xyz, t, rf, orbit, phase)[0]
    y = fit.fold(f + np.array([115_000, -55_000, -40_000, 21_000])[group] + 960 * (rf / 1e9 - 11.5))
    factors = [fit.Factor(*item) for item in zip(t, rf, y, orbit, group, strict=True)]
    result, residuals = fit.solve(factors, SimpleNamespace(duration_s=120), {"center": [0, 0]})
    c0, free = result["arms"].values()
    assert c0["c_hz_per_ghz"] == 0.0 and abs(free["c_hz_per_ghz"] - 960) < 15
    assert result["status"] == "withheld" and c0["latlon"] is None
    assert free["held_points"] == c0["held_points"] and free["held_points"] > 0
    assert free["held_rms_hz"] < c0["held_rms_hz"]
    assert distance_km(free["forced_latlon"], expected.tolist()) < 0.2
    assert len(residuals["c0"]) == len(factors)


def test_rejects_future_catalogue_before_parsing():
    source = fit.Catalogue(b"", 5, 4, 6, 120)
    with pytest.raises(ValueError, match="causal"):
        fit.orbit_table(source, set(), [0, 0])
