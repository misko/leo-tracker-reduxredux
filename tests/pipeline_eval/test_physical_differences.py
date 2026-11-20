import numpy as np
import pytest

from tools.pipeline_eval.qualification import physical_differences as measured
from tools.pipeline_eval.qualification import physical_differences_solver as model


def test_exact_simultaneous_pairs_exclude_comb_copies_and_reuse_no_curve():
    t = np.linspace(100, 108, 25)
    clean = t**2
    shifted = clean + measured.COMB_HZ
    distinct = -400 * t
    # Interpolation would form a match to the last curve, but exact clock support would not.
    pairs, audit = measured.simultaneous(
        [(t, clean), (t, shifted), (t, distinct), (t + 1e-7, clean)]
    )
    assert len(pairs) == 1
    assert len(pairs[0]["times"]) == 24
    assert any(x["harmonic_like"] and not x["eligible"] for x in audit)
    assert sum(x["selected"] for x in audit) == 1
    assert not any(3 in x["track_rows"] for x in audit)


def test_prepare_keeps_original_timestamp_when_consolidating_repeated_bins():
    times = np.arange(6.0)
    raw = np.column_stack((np.concatenate((times, [3, 3])), [10, 11, 12, 13, 14, 15, 18, 3]))
    out_t, out_v = measured.consolidate(raw)
    assert np.array_equal(out_t, times)
    assert out_v[3] == 13


def test_pair_projection_cancels_common_time_varying_error_but_retains_differential_rate():
    t = np.arange(20.0)
    shared = 15_000 * np.sin(t) + 20 * t**2
    y = model.centered((10 * t + 500 + shared) - (-5 * t - 2000 + shared))
    assert y == pytest.approx(model.centered(15 * t))
    assert np.ptp(y) > 0
    p = model.affine_basis(t)
    assert np.allclose(p.T @ t, 0)
    assert np.allclose(p.T @ np.ones_like(t), 0)


def test_shuffle_preserves_same_time_spans_and_frequency_sequence():
    first = dict(times=[10, 18], first_hz=[10, 20], second_hz=[18, 14])
    second = dict(first, times=[800, 808])
    shuffled = measured.shuffled([first, second], 900)
    assert shuffled[0] == dict(first, times=[190, 198])
    assert shuffled[1] == dict(second, times=[620, 628])


def test_joint_match_holds_identity_on_unseen_samples_and_forbids_reusing_an_orbit(monkeypatch):
    a = np.r_[np.linspace(20, 4000, 13), np.linspace(6000, 10000, 7)]
    b = -np.r_[np.linspace(20, 2500, 13), np.linspace(3000, 5000, 7)]
    same = np.zeros(len(a))
    measured = np.r_[model.centered(a[:13] - b[:13]), model.centered(b[13:] - a[13:])]

    def as_geometry(p, _v, _location, _up, _rf):
        return p, np.ones_like(p, dtype=bool)

    monkeypatch.setattr(model, "geometry", as_geometry)
    left = model.Side(np.stack((a, b, same)), np.empty(0), np.arange(3))
    right = model.Side(np.stack((a, b, same)), np.empty(0), np.arange(3))
    pair = model.Pair(left, right, 13, measured, 11_325_000_000, 3)
    match = model.assign(pair, None, None)
    assert match.orbit_rows == (0, 1)
    assert match.training == 0
    assert match.held > 1
    zeros = model.Pair(left, right, 13, np.zeros(20), 11_325_000_000, 3)
    result = model.assign(zeros, None, None)
    assert result.orbit_rows[0] != result.orbit_rows[1]


def test_missing_coincident_pairs_withholds_both_arms_without_position_guess():
    result = model.solve({"pairs": []}, "unused", tile=[0, 1])
    assert result["reason"] == "no_eligible_coincident_pairs"
    assert (
        result["arms"]["c0"]
        == result["arms"]["fitted_c"]
        == {"latlon": None, "forced_latlon": None}
    )


def test_conditioning_requires_spatial_information_on_both_axes(monkeypatch):
    t = np.arange(24.0)

    def fake_sites(_tile, points):
        return points, points, None

    def projected(p, _v, position, _up, _rf):
        return p @ position, np.ones(len(p), dtype=bool)

    monkeypatch.setattr(model.grid, "_sites", fake_sites)
    monkeypatch.setattr(model, "geometry", projected)
    velocities = np.zeros((1, len(t), 2))
    zero = model.Side(np.zeros_like(velocities), velocities, np.array([2]))

    def edge(x, y):
        values = np.column_stack((x * t, y * t))
        side = model.Side(values[None, :, :], velocities, np.array([1]))
        pair = model.Pair(side, zero, 16, np.zeros(24), 11_325_000_000, 2)
        return model.Match(0, 0, 2, pair, (0, 0))

    singular, worst = model.conditioner([edge(1, 0)], None, np.zeros(2))
    assert singular[0] > 0 and singular[1] == 0
    assert worst is None
    singular, worst = model.conditioner([edge(1, 0), edge(0, 1)], None, np.zeros(2))
    assert singular[0] == pytest.approx(singular[1])
    assert worst == pytest.approx(1 / singular[1])
