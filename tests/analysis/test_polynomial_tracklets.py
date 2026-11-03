"""Independent recovery checks for unlabeled, aliased frequency trajectories.

These controls use known identities rather than treating a small training RMS
as evidence that the assignments are physically coherent.
"""

from dataclasses import replace

import numpy as np
import pytest
from numpy.polynomial.legendre import legval

from leo.analysis.polynomial_tracklets import TrackConfig, _bounded_slope, fit_lane

PERIOD = 1 / 4.4e-6


def wrap(frequency):
    return (np.asarray(frequency) + PERIOD / 2) % PERIOD - PERIOD / 2


def assert_membership_integrity(result, time, frequency):
    """Check independent index, polynomial, and integer-lift consistency."""
    assigned = np.asarray(result["assignment"])
    lifts = np.asarray(result["alias_lifts"])
    assert assigned.shape == lifts.shape == time.shape
    assert np.issubdtype(assigned.dtype, np.integer)
    assert np.issubdtype(lifts.dtype, np.integer)
    assert np.all(assigned >= -1)
    all_indices = []
    for track_index, track in enumerate(result["tracks"]):
        indices = np.asarray(track["indices"], dtype=int)
        assert len(indices) == len(np.unique(indices))
        assert np.all((indices >= 0) & (indices < len(time)))
        assert np.all(assigned[indices] == track_index)
        all_indices.extend(indices.tolist())
        piece_indices = []
        residuals = []
        for piece in track["pieces"]:
            ix = np.asarray(piece["indices"], dtype=int)
            degree = piece["degree"]
            assert 0 <= degree <= 4
            assert len(piece["coefficients_hz"]) == degree + 1
            assert piece["time_scale_s"] > 0
            x = (time[ix] - piece["reference_time_s"]) / piece["time_scale_s"]
            prediction = legval(x, piece["coefficients_hz"])
            residual = frequency[ix] + PERIOD * lifts[ix] - prediction
            # Lift convention is y + k*A = prediction + measurement noise.
            np.testing.assert_allclose(residual, wrap(frequency[ix] - prediction), atol=1e-6)
            residuals.extend(residual.tolist())
            piece_indices.extend(ix.tolist())
        ordered = sorted(track["pieces"], key=lambda piece: time[piece["indices"]].min())
        for left, right in zip(ordered, ordered[1:], strict=False):
            boundary = left["join_time_s"]
            assert boundary == right["join_time_s"]
            values, slopes = [], []
            for piece in (left, right):
                x = (boundary - piece["reference_time_s"]) / piece["time_scale_s"]
                coefficients = np.asarray(piece["coefficients_hz"])
                values.append(legval(x, coefficients))
                slopes.append(
                    legval(x, np.polynomial.legendre.legder(coefficients)) / piece["time_scale_s"]
                )
            assert values[0] == pytest.approx(values[1], abs=1e-4)
            assert slopes[0] == pytest.approx(slopes[1], abs=1e-4)
        assert sorted(piece_indices) == sorted(indices.tolist())
        assert track["start_s"] == pytest.approx(float(time[indices].min()))
        assert track["end_s"] == pytest.approx(float(time[indices].max()))
        assert track["residual_rms_hz"] == pytest.approx(
            np.sqrt(np.mean(np.square(residuals))), rel=1e-5, abs=1e-5
        )
    assert len(all_indices) == len(set(all_indices))
    assert sorted(all_indices) == np.flatnonzero(assigned >= 0).tolist()


def test_wrapped_arc_recovers_signal_with_consistent_lifts():
    rng = np.random.default_rng(4001)
    time = np.linspace(0, 48, 145)
    truth = 125_000 - 1_500 * time
    frequency = wrap(truth + rng.normal(0, 35, len(time)))
    result = fit_lane(time, frequency)
    assert_membership_integrity(result, time, frequency)
    assert np.mean(np.asarray(result["assignment"]) >= 0) > 0.9
    assert len(result["tracks"]) <= 3
    assert max(track["residual_rms_hz"] for track in result["tracks"]) < 150
    # An alias boundary alone must not fragment a densely supported line.
    assert max(len(track["indices"]) for track in result["tracks"]) > 0.8 * len(time)


def test_crossing_tracks_are_not_pooled_and_clutter_is_not_forced():
    rng = np.random.default_rng(4002)
    base_time = np.linspace(0, 48, 100)
    time = np.concatenate([base_time, base_time + 0.01, rng.uniform(0, 48, 70)])
    truth = np.concatenate(
        [
            90_000 - 1_400 * base_time,
            22_800 + 1_400 * base_time,
            rng.uniform(-PERIOD / 2, PERIOD / 2, 70),
        ]
    )
    frequency = wrap(truth + rng.normal(0, 35, len(time)))
    identity = np.concatenate([np.zeros(100, int), np.ones(100, int), np.full(70, -1)])
    result = fit_lane(time, frequency)
    assert_membership_integrity(result, time, frequency)
    assigned = np.asarray(result["assignment"])
    assert np.mean(assigned[:200] >= 0) > 0.8
    assert np.mean(assigned[200:] >= 0) < 0.35
    # Crossings can leave ambiguous points, but cannot merge both identities.
    correct = 0
    for track in result["tracks"]:
        labels = identity[np.asarray(track["indices"], int)]
        signal = labels[labels >= 0]
        if len(signal):
            dominant = np.bincount(signal, minlength=2).max()
            assert dominant / len(signal) > 0.9
            correct += dominant
    assert correct > 160


def test_curvature_is_supported_without_excessive_fragmentation():
    rng = np.random.default_rng(4003)
    time = np.linspace(0, 60, 181)
    centered = time - 30
    frequency = wrap(70_000 - 900 * centered + 12 * centered**2 + rng.normal(0, 30, len(time)))
    result = fit_lane(time, frequency)
    assert_membership_integrity(result, time, frequency)
    assert np.mean(np.asarray(result["assignment"]) >= 0) > 0.85
    assert len(result["tracks"]) <= 4
    assert any(piece["degree"] >= 2 for track in result["tracks"] for piece in track["pieces"])


def test_real_frequency_step_is_not_hidden_inside_a_smooth_piece():
    rng = np.random.default_rng(4004)
    time = np.linspace(0, 60, 181)
    frequency = wrap(50_000 - 700 * time + 20_000 * (time >= 30) + rng.normal(0, 30, len(time)))
    result = fit_lane(time, frequency)
    assert_membership_integrity(result, time, frequency)
    assert np.mean(np.asarray(result["assignment"]) >= 0) > 0.8
    for track in result["tracks"]:
        for piece in track["pieces"]:
            supported = time[np.asarray(piece["indices"], int)]
            assert not (np.any(supported < 27) and np.any(supported > 33))


def test_supported_quartic_uses_higher_degree_and_predicts_excluded_points():
    rng = np.random.default_rng(4006)
    time = np.linspace(0, 60, 241)
    x = (time - 30) / 30
    truth = 50_000 + 20_000 * x - 10_000 * x**2 + 4_000 * x**3 + 8_000 * x**4
    frequency = wrap(truth + rng.normal(0, 35, len(time)))
    # Exclude a contiguous time block from coefficient fitting and selection.
    train = ~((time > 25) & (time < 31))
    result = fit_lane(time[train], frequency[train])
    assert_membership_integrity(result, time[train], frequency[train])
    assert np.mean(np.asarray(result["assignment"]) >= 0) > 0.85
    assert any(piece["degree"] >= 3 for track in result["tracks"] for piece in track["pieces"])
    squared_errors = []
    for t, true_frequency in zip(time[~train], truth[~train], strict=True):
        candidates = []
        for track in result["tracks"]:
            for piece in track["pieces"]:
                observed_time = time[train][piece["indices"]]
                if observed_time.min() <= t <= observed_time.max():
                    coordinate = (t - piece["reference_time_s"]) / piece["time_scale_s"]
                    predicted = legval(coordinate, piece["coefficients_hz"])
                    candidates.append(abs(wrap(predicted - true_frequency)))
        if candidates:
            squared_errors.append(min(candidates) ** 2)
    assert len(squared_errors) > 0.8 * (~train).sum()
    assert np.sqrt(np.mean(squared_errors)) < 150


def test_long_unobserved_gap_is_not_asserted_continuous():
    rng = np.random.default_rng(4007)
    time = np.concatenate([np.linspace(0, 20, 61), np.linspace(80, 100, 61)])
    frequency = wrap(110_000 - 1_600 * time + rng.normal(0, 35, len(time)))
    config = TrackConfig()
    result = fit_lane(time, frequency, config)
    assert_membership_integrity(result, time, frequency)
    assert np.mean(np.asarray(result["assignment"]) >= 0) > 0.9
    for track in result["tracks"]:
        assert np.diff(np.sort(time[np.asarray(track["indices"], int)])).max() <= config.max_gap_s


def test_uniform_clutter_does_not_manufacture_supported_tracks():
    rng = np.random.default_rng(4008)
    time = np.sort(rng.uniform(0, 90, 200))
    frequency = rng.uniform(-PERIOD / 2, PERIOD / 2, len(time))
    result = fit_lane(time, frequency)
    assert_membership_integrity(result, time, frequency)
    assert np.mean(np.asarray(result["assignment"]) >= 0) < 0.1


def test_default_noise_scale_retains_realistic_measurement_scatter():
    rng = np.random.default_rng(4009)
    time = np.linspace(0, 60, 181)
    frequency = wrap(120_000 - 1_400 * time + rng.normal(0, 150, len(time)))
    result = fit_lane(time, frequency)
    assert_membership_integrity(result, time, frequency)
    assert np.mean(np.asarray(result["assignment"]) >= 0) > 0.85
    assert max(len(track["indices"]) for track in result["tracks"]) > 0.7 * len(time)


def test_continuous_curvature_change_is_joined_without_structured_residuals():
    rng = np.random.default_rng(4010)
    time = np.linspace(0, 60, 241)
    centered = time - 30
    truth = (
        50_000 - 1_000 * centered
        + np.where(centered < 0, 25 * centered**2, -25 * centered**2)
    )
    frequency = wrap(truth + rng.normal(0, 35, len(time)))
    result = fit_lane(time, frequency)
    assert_membership_integrity(result, time, frequency)
    assert np.mean(np.asarray(result["assignment"]) >= 0) > 0.9
    joined = [track for track in result["tracks"] if len(track["pieces"]) > 1]
    assert joined, "A C1 piecewise quadratic should not become overlapping structured quartics"
    largest = max(joined, key=lambda track: len(track["indices"]))
    assert len(largest["indices"]) > 0.8 * len(time)
    assert not largest["diagnostics"]["quality_flags"]
    for piece in largest["pieces"]:
        ix = np.asarray(piece["indices"], int)
        ix = ix[np.argsort(time[ix])]
        x = (time[ix] - piece["reference_time_s"]) / piece["time_scale_s"]
        residuals = wrap(frequency[ix] - legval(x, piece["coefficients_hz"]))
        assert abs(np.corrcoef(residuals[:-1], residuals[1:])[0, 1]) < 0.4


def test_input_order_and_global_alias_branch_do_not_change_recovery():
    rng = np.random.default_rng(4005)
    time = np.linspace(0, 48, 121)
    frequency = wrap(125_000 - 1_350 * time + rng.normal(0, 35, len(time)))
    reference = fit_lane(time, frequency)
    permutation = rng.permutation(len(time))
    permuted = fit_lane(time[permutation], frequency[permutation])
    shifted = fit_lane(time, frequency + 3 * PERIOD)
    assert_membership_integrity(permuted, time[permutation], frequency[permutation])
    assert_membership_integrity(shifted, time, frequency + 3 * PERIOD)
    base_assignment = np.asarray(reference["assignment"])
    restored_assignment = np.asarray(permuted["assignment"])[np.argsort(permutation)]
    shifted_assignment = np.asarray(shifted["assignment"])
    for assignment in (restored_assignment, shifted_assignment):
        np.testing.assert_array_equal(base_assignment >= 0, assignment >= 0)
        # Track labels may be renumbered; memberships must still agree.
        np.testing.assert_array_equal(
            base_assignment[:, None] == base_assignment[None, :],
            assignment[:, None] == assignment[None, :],
        )


def test_empty_and_insufficient_support_do_not_create_interpolating_tracks():
    assert fit_lane(np.array([]), np.array([]))["tracks"] == []
    time = np.array([0.0, 1.0, 2.0, 3.0])
    frequency = np.array([500.0, -20_000.0, 90_000.0, 60_000.0])
    result = fit_lane(time, frequency)
    assert result["tracks"] == []
    np.testing.assert_array_equal(result["assignment"], -np.ones(len(time), dtype=int))


def test_mismatched_observation_shapes_are_rejected():
    with pytest.raises(ValueError):
        fit_lane(np.array([0, 1]), np.array([0]), TrackConfig())


def test_nonfinite_observations_retain_original_indices_and_remain_unresolved():
    rng = np.random.default_rng(4011)
    time = np.linspace(0, 48, 145)
    frequency = wrap(125_000 - 1_500 * time + rng.normal(0, 35, len(time)))
    time[10] = np.nan
    frequency[50] = np.inf
    result = fit_lane(time, frequency)
    assert_membership_integrity(result, time, frequency)
    assert result["diagnostics"]["nonfinite_points"] == 2
    assert result["assignment"][10] == result["assignment"][50] == -1
    assert result["alias_lifts"][10] == result["alias_lifts"][50] == 0
    assert np.mean(np.asarray(result["assignment"]) >= 0) > 0.9


@pytest.mark.parametrize(
    "changes",
    [
        {"noise_sigma_hz": np.nan},
        {"noise_sigma_hz": np.inf},
        {"noise_sigma_hz": 0},
        {"association_sigma": np.inf},
        {"association_sigma": 0},
        {"max_degree": -1},
        {"max_degree": 5},
        {"max_degree": 1.5},
        {"seed_trials": 0},
        {"max_proposals": -1},
        {"max_tracks": 0},
        {"window_lengths_s": ()},
        {"window_lengths_s": (0,)},
        {"window_lengths_s": (np.nan,)},
        {"track_penalty": -1},
        {"points_per_coefficient": 1},
    ],
)
def test_invalid_configuration_is_rejected(changes):
    with pytest.raises(ValueError):
        replace(TrackConfig(), **changes)


@pytest.mark.parametrize("sign", [-1, 1])
@pytest.mark.parametrize("scale", [1.0, 5.0])
@pytest.mark.parametrize(("peak", "allowed"), [(4000.1, False), (3999.9, True)])
def test_slope_bound_checks_interior_extrema_between_observation_times(sign, scale, peak, allowed):
    """A cubic's peak slope need not occur on either the data or a fixed grid."""
    offset = 0.015
    reference = 40.0
    time = reference + scale * np.array([-1.0, 1.0])
    # Analytically, dp/dt = sign * (peak - 1000 * (x - offset)**2).
    power_coefficients = sign * scale * np.array(
        [0.0, peak - 1000 * offset**2, 1000 * offset, -1000 / 3]
    )
    piece = {
        "indices": np.arange(2),
        "degree": 3,
        "reference_time_s": reference,
        "time_scale_s": scale,
        "coefficients_hz": np.polynomial.legendre.poly2leg(power_coefficients),
    }
    # Both sides of the 4000 Hz/s boundary evade the former 32-point grid.
    grid = np.linspace(-1, 1, 32)
    assert np.max(np.abs(peak - 1000 * (grid - offset) ** 2)) < 4000
    assert _bounded_slope(piece, time, TrackConfig()) is allowed
