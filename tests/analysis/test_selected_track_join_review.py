"""Shared-constant checks cannot hide distinct aliases, offsets or pooled trends."""

import importlib
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def review(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    return importlib.import_module("review_dsx01_selected_track_joins").evaluate_join


def fixture(starts=(0, 40), offsets=(350.0, 350.0), aliased=False):
    times = np.arange(0.0, max(starts) + 21)
    physical = 20000 - 400 * times + 3 * times**2
    tracks = []
    for i, (start, offset) in enumerate(zip(starts, offsets, strict=True)):
        t = np.arange(start, start + 21, dtype=float)
        ix = np.searchsorted(times, t)
        tracks.append(
            dict(
                key=f"track{i}",
                receiver=1,
                channel=1,
                rf_hz=11.5e9,
                times=t,
                values=physical[ix]
                + offset
                + 20 * np.sin(t)
                + (1 / 4.4e-6 if aliased and i == 1 else 0),
                observation_ids=[f"{i}:{j}" for j in range(len(t))],
            )
        )
    return tracks, times, physical


def evaluate(review, tracks, times, frequency):
    return review(
        tracks,
        times,
        frequency,
        np.full_like(frequency, 45.0),
        np.zeros(8),
        np.arange(123, 123 + len(frequency)),
        np.ones(len(frequency), bool),
        np.ones(4, bool),
    )


def test_real_continuation_retains_all_points_and_fragment_aliases(review):
    tracks, times, physical = fixture(aliased=True)
    # The second candidate can fit the fragments separately, but needs two constants.
    wrong = physical + 1400 * (times > 30)
    result = evaluate(review, tracks, times, np.array([physical, wrong]))
    assert result["points"] == 42
    assert result["passing_candidates"].tolist() == [123]
    assert result["join_favored"]
    best = result["candidates"][0]
    assert best["rms_hz"] < 25
    assert best["native_aliases"].tolist() == [0, -1]
    assert best["separate_minus_joined_cost"] > 0

    module = importlib.import_module("review_dsx01_selected_track_joins")
    for i, member in enumerate(best["members"]):
        displayed = module.shared_alias_frame(
            member["observed_hz"], best["native_aliases"][i], best["native_aliases"][0]
        )
        # Both displayed fragments follow the same physical curve, even when
        # their original CFOs differ by a whole native ambiguity period.
        expected = 20000 - 400 * member["time_s"] + 3 * member["time_s"] ** 2
        np.testing.assert_allclose(displayed, expected + 350, atol=21)
        shifted_prediction = module.shared_alias_frame(
            member["predicted_hz"], best["native_aliases"][i], best["native_aliases"][0]
        )
        np.testing.assert_allclose(displayed - shifted_prediction, member["residual_hz"], atol=1e-8)


def test_independent_offsets_do_not_force_a_join(review):
    tracks, times, physical = fixture(offsets=(350, 1750))
    result = evaluate(review, tracks, times, np.array([physical]))
    assert result["passing_candidates"].size == 0
    assert not result["join_favored"]
    assert result["points"] == 42


def test_pooled_screen_detects_a_trend_across_individually_acceptable_fragments(review):
    tracks, times, physical = fixture(
        starts=(0, 30, 60, 90, 120, 150),
        offsets=tuple(350 + d for d in (-45, -27, -9, 9, 27, 45)),
    )
    result = evaluate(review, tracks, times, np.array([physical]))
    row = result["candidates"][0]
    assert all(m["diagnostics"]["noise_screen_pass"] for m in row["members"])
    assert not row["pooled_diagnostics"]["noise_screen_pass"]
    assert result["passing_candidates"].size == 0


def test_duplicate_observation_ownership_is_rejected(review):
    tracks, times, physical = fixture()
    tracks[1]["observation_ids"] = tracks[0]["observation_ids"]
    with pytest.raises(ValueError, match="duplicate observation"):
        evaluate(review, tracks, times, np.array([physical]))
