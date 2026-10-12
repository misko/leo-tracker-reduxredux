import numpy as np
import pytest

from leo.analysis.clock_conditioned_bootstrap import (
    ClockConditioningConfiguration,
    bootstrap_with_clock_conditioning,
)
from leo.analysis.continuous_merge_bootstrap import (
    ContinuousBootstrapPolicy,
    bootstrap_with_continuity,
)
from leo.contracts.regional_position import PositionObservations, PositionOrbitBank, RegionalPrior


def functions(times):
    return np.column_stack(
        (
            -100000 + 100 * times + 0.03 * times**2,
            100000 + 120 * times + 0.05 * times**2,
            10000 + 400 * times + 2 * times**2,
        )
    )


def predictor(bank, observations, prior, point, shifts_s, *, derivatives=False):
    prediction = functions(observations.times_s)[:, bank.numbers - 100]
    return prediction, np.ones_like(prediction, bool), None, None


def fixture():
    tracks, times, receivers, values = [], [], [], []
    for rx in (0, 1):
        for candidate, duration in ((0, 20), (2, 100), (2, 100)):
            t = np.linspace(0, duration, 80)
            rows = tuple(range(len(times), len(times) + len(t)))
            tracks.append(rows)
            times.extend(t)
            receivers.extend([rx] * len(t))
            values.extend(functions(t)[:, candidate] + 2000 + (12 if rx == 0 else -8) * (t - 50))
    count = len(times)
    observations = PositionObservations(
        tuple(str(i) for i in range(count)),
        np.array(times),
        np.array(values),
        np.full(count, 11.2e9),
        np.array(receivers),
        np.ones(count),
        np.ones(count),
    )
    bank = PositionOrbitBank(
        np.arange(100, 103), np.array([-20, 120]), np.zeros((3, 2, 3)), np.zeros((3, 2, 3))
    )
    return observations, bank, RegionalPrior(), tuple(tracks)


def test_alternation_recovers_ambiguous_candidate_and_known_shared_drift():
    obs, bank, prior, tracks = fixture()
    control = bootstrap_with_continuity(
        obs,
        bank,
        prior,
        [0, 0],
        tracks,
        merged_tracks=(),
        maximum_seconds=10,
        orbit_predictor=predictor,
    )
    assert next(m for m in control.matches if m.rows == tracks[0]).satellite_index == 1
    receipts = []
    result = bootstrap_with_clock_conditioning(
        obs,
        bank,
        prior,
        [0, 0],
        tracks,
        merged_tracks=(),
        maximum_seconds=10,
        orbit_predictor=predictor,
        audit=receipts.append,
    )
    assert next(m for m in result.matches if m.rows == tracks[0]).satellite_index == 0
    np.testing.assert_allclose(result.vector[[3, 5]], [12, -8], atol=0.01)
    assert len(receipts[0]["branches"]) == 3
    assert len(receipts[0]["branches"][0]["passes"]) == 3


def test_no_conditioning_repeats_old_initializer_exactly_without_changing_input():
    obs, bank, prior, tracks = fixture()
    before = obs.measured_hz.copy()
    control = bootstrap_with_continuity(
        obs,
        bank,
        prior,
        [0, 0],
        tracks,
        merged_tracks=(),
        maximum_seconds=10,
        orbit_predictor=predictor,
    )
    result = bootstrap_with_clock_conditioning(
        obs,
        bank,
        prior,
        [0, 0],
        tracks,
        merged_tracks=(),
        configuration=ClockConditioningConfiguration(conditioning="none"),
        maximum_seconds=10,
        orbit_predictor=predictor,
    )
    np.testing.assert_array_equal(result.vector, control.vector)
    assert result.matches == control.matches
    np.testing.assert_array_equal(obs.measured_hz, before)


def test_restored_physical_slope_and_centered_intercept_are_exact_for_one_pass():
    obs, bank, prior, tracks = fixture()
    result = bootstrap_with_clock_conditioning(
        obs,
        bank,
        prior,
        [0, 0],
        tracks,
        merged_tracks=(),
        configuration=ClockConditioningConfiguration(passes=1, starts_hz_per_s=((0.0, 0.0),)),
        maximum_seconds=10,
        orbit_predictor=predictor,
    )
    control = bootstrap_with_continuity(
        obs,
        bank,
        prior,
        [0, 0],
        tracks,
        merged_tracks=(),
        maximum_seconds=10,
        orbit_predictor=predictor,
    )
    np.testing.assert_array_equal(result.vector, control.vector)


def test_invalid_controls_and_total_budget_are_explicit():
    for kwargs in (
        {"conditioning": "unknown"},
        {"passes": 0},
        {"damping": 0},
        {"maximum_slope_hz_per_s": np.inf},
    ):
        with pytest.raises(ValueError):
            ClockConditioningConfiguration(**kwargs)
    obs, bank, prior, tracks = fixture()
    with pytest.raises(TimeoutError):
        bootstrap_with_clock_conditioning(
            obs,
            bank,
            prior,
            [0, 0],
            tracks,
            merged_tracks=(),
            maximum_seconds=1e-12,
            orbit_predictor=predictor,
        )


def test_consistent_join_retains_original_discovery_candidates_each_pass():
    obs, bank, prior, tracks = fixture()
    split = (tracks[1][:40], tracks[1][40:], *tracks[:1], *tracks[2:])
    receipts = []
    result = bootstrap_with_clock_conditioning(
        obs,
        bank,
        prior,
        [0, 0],
        split,
        merged_tracks=(tracks[1],),
        policy=ContinuousBootstrapPolicy(mode="consistent", rms_floor_hz=1000),
        maximum_seconds=10,
        orbit_predictor=predictor,
        audit=receipts.append,
    )
    assert any(m.rows == tracks[1] for m in result.matches)
    chosen = receipts[0]["branches"][receipts[0]["selected_branch"]]
    assert all(p["proposal_audit"]["selected_joins"] == 1 for p in chosen["passes"])
    assert len(obs.window_ids) == len(set(obs.window_ids))
