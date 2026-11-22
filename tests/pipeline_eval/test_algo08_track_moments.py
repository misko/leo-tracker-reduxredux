from types import SimpleNamespace

import numpy as np

from leo.analysis.localization_v3 import discovery, scan
from leo.analysis.research.retained_track_likelihood import profile, whitening
from leo.analysis.research.shared_orbit_phase_fit import augment_phase_statistics
from tools.pipeline_eval.variants import algo08_track_moments as proposal, v5_core


def orbit_curves(times):
    t = times % proposal.BIN_SECONDS
    return np.vstack((40_000 - 900 * t + 6 * t**2, -240_000 + 3000 * t - t**2))


def test_profile_preserves_off_node_observations_and_folded_alias():
    times = np.r_[np.arange(20.0), np.arange(20.25, 34, 1.25), 44, 45]
    moments = proposal.track_moments(times)
    observed = orbit_curves(times)[0] + 2000 + 80 * np.cos(times)
    observed[6] += 700
    assert times[6] not in moments.nodes
    assert len(moments.nodes) == 8
    exact = profile(observed, orbit_curves(times), *whitening(times))
    compressed = proposal.profile(moments, observed, orbit_curves(moments.nodes))
    for key in ("rms", "cost", "bias"):
        np.testing.assert_allclose(compressed[key], exact[key], rtol=1e-12, atol=1e-10)


def test_local_polynomials_reproduce_phase_statistics(monkeypatch):
    t = np.r_[np.arange(18.0), 20.5, 22, 24, 26, 29, 32, 35]
    tracks = [dict(key="irregular", times=t, values=np.sin(t) * 1000,
                   channel=5, receiver=2, rf_hz=12.5e9)]
    groups = [("irregular", tracks)]
    full = SimpleNamespace(
        tracks=tracks, curved=[0], times=t, norads=np.array([1, 2]), sky=object()
    )
    monkeypatch.setattr(scan, "prepare_phase_geometry", lambda bank, times: (bank, times))
    detail = {}
    compact = proposal.MomentDiscovery(full, detail)

    def inputs(times):
        elevation = np.ones((2, len(times)))
        elevation[1, -1] = -1
        return dict(time_s=times, doppler_0=orbit_curves(times), elevation_deg=elevation)

    full_bank = inputs(t)
    corrections = {"5": -1400.}
    exact = discovery.statistics(groups, full_bank, corrections)
    # The exact helper expects the corrected observations used to build the
    # residual stats when computing the Doppler/phase cross term.
    exact["fragments"] = [dict(tracks[0], values=tracks[0]["values"] - corrections["5"])]
    exact = augment_phase_statistics(exact, t, full_bank["doppler_0"], orbit_curves(t) / 19)
    nodes = compact.scan.times
    moment_bank = inputs(nodes)
    moment_stats = compact.statistics(groups, moment_bank, corrections)
    moment_stats = compact.phase_statistics(moment_stats, nodes, moment_bank["doppler_0"],
                                            orbit_curves(nodes) / 19)
    for key in ("n", "mx", "xx", "g", "q", "mean", "xz", "rss", "visible", "hm", "hh", "xh", "zh"):
        np.testing.assert_allclose(moment_stats[key], exact[key], rtol=1e-12, atol=1e-10)
    assert detail["full_curved_points"] == len(t)
    assert detail["moment_nodes"] == len(nodes) < len(t)
    assert compact.scan.tracks is full.tracks
    assert full.times is t


def test_full_scan_fits_all_finalists_and_restores_full_geometry_on_empty_gate(monkeypatch):
    times = np.arange(30.0)
    full = SimpleNamespace(
        tracks=[dict(key="track", times=times)], curved=[0], times=times,
        norads=np.array([101, 202]), sky=object(), geometry=None,
    )
    monkeypatch.setattr(scan, "prepare_phase_geometry", lambda bank, knots: (bank, knots))
    finalists = [
        dict(seed=dict(rows=[dict(component="track", candidate_index=j, candidate_norad=100 + j)]),
             aliases=[0])
        for j in range(4)
    ]
    monkeypatch.setattr(proposal.MomentDiscovery, "rank", lambda discovery: finalists)

    def fit(received, branches):
        assert received is full
        assert received.geometry is None
        assert branches == finalists[:3]
        return {"choices": [{"arms": {"c0": {"metrics": {"accepted_points": 0}}}}]}, 3

    def stock(received):
        assert received is full
        assert received.geometry[1] is times
        return "stock answer", 2

    monkeypatch.setattr(v5_core, "fit_initial_nodes", fit)
    monkeypatch.setattr(v5_core, "initial_selection", stock)
    detail = {}
    assert proposal.select(full, detail) == ("stock answer", 2)
    assert detail["fallback"] == "empty_full_data_gate"
