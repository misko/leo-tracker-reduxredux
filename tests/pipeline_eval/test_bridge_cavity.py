from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.qualification import bridge_cavity_eval as study
from tools.pipeline_eval.variants.bridge_cavity import (
    SeedUnavailable,
    center_seed,
    detrended_profile,
)


def make_scan():
    tracks = [
        dict(key=f"curve-{i}", rf_hz=11.5e9, times=np.arange(3.0), values=np.full(3, float(i)))
        for i in range(3)
    ]
    return SimpleNamespace(
        geometry="causal fixed sky",
        search_region=SimpleNamespace(center=(37.0, -122.0)),
        curved=[0, 1, 2],
        tracks=tracks,
        index=[np.arange(3)] * 3,
        norads=np.array([110, 220, 330]),
        sigma=np.array([1.0, 1, 2]),
        radio_sigma_hz=120,
    )


def zero_state(scan):
    return {"phases": np.zeros(len(scan.norads))}


def test_seed_uses_only_visible_causal_profiles_then_pools_active_phase():
    scan = make_scan()
    visits = []

    def projection(grid, lat, lon):
        assert grid == scan.geometry and (lat, lon) == scan.search_region.center
        return (
            np.array([[1.0] * 3, [2.0] * 3, [3.0] * 3]),
            np.array([[1.0] * 3, [-1.0] * 3, [1.0] * 3]),
            np.ones((3, 3)),
        )

    def profile(raw, f, h, times, sigma, prior):
        assert sigma == 120 and times.tolist() == [0, 1, 2]
        assert f[:, 0].tolist() == [1.0, 3.0] and prior.tolist() == [1.0, 2.0]
        visits.append(raw[0])
        return dict(
            cost=np.array([5.0, 1.0]),
            aliases=[1, -4],
            rms_hz=[30.0, 460.0 if raw[0] == 2 else 81.0],
            phase_s=[3.0, float(raw[0]) * 2 + 1],
        )

    node, keep = center_seed(scan, projection, profile, zero_state)
    assert visits == [0, 1, 2]
    assert [r["candidate_norad"] for r in node["seed"]["rows"]] == [330, 330, 330]
    assert node["aliases"] == [-4, -4, -4]
    assert keep.tolist() == [True] * 6 + [False] * 3
    assert node["seed"]["state"]["phases"].tolist() == [0.0, 0.0, 2.0]


def test_detrended_seed_discriminates_curvature_through_large_offset_and_drift():
    times = np.linspace(-30, 30, 61)
    correct = 1000 + 40 * times + 1.5 * times**2
    wrong = 1000 + 50 * times - 0.05 * times**3
    frequency = np.array([wrong, correct])
    slope = np.array([0.01 * times**2, 0.1 * times + 0.01 * times**2])
    widths = np.ones(2)
    period = 100_000.0
    y = correct + 0.5 * slope[1]
    neutral = detrended_profile(y, frequency, slope, times, 100, widths, period)
    shifted = detrended_profile(
        y + 2 * period + 12_000 + 140 * times, frequency, slope, times, 100, widths, period
    )
    assert np.allclose(neutral["cost"], shifted["cost"], rtol=1e-9, atol=1e-9)
    assert np.argmin(shifted["cost"]) == 1
    assert shifted["aliases"][1] == -2


def test_no_visible_support_withholds_the_joint_seed():
    scan = make_scan()

    def invisible(*args):
        return np.ones((3, 3)), -np.ones((3, 3)), np.ones((3, 3))

    def unexpected(*args):
        pytest.fail("below-horizon hypotheses must not be profiled")

    with pytest.raises(SeedUnavailable, match="no acceptable curved support"):
        center_seed(scan, invisible, unexpected, zero_state)


def test_blind_holdout_selection_uses_ids_alone_and_excludes_diagnostics():
    cases = [*study.TIMING_IDS, *study.DIAGNOSTIC, "DS26-0313", "DS26-0279", "DS29-0604"]
    assert study.select_holdouts({i: {"arbitrary": 10} for i in cases}) == (
        "DS26-0313",
        "DS26-0279",
        "DS29-0604",
    )
    assert study.select_holdouts(list(reversed(cases))) == ("DS26-0313", "DS26-0279", "DS29-0604")
