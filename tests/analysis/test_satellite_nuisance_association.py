from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from leo.analysis.research.satellite_nuisance_association import (
    MeasurementTrack,
    chronological_block_mask,
    chronological_mask,
    fit_hierarchical_candidates,
    fit_independent_path_linear_null,
    fit_offset_candidates,
    fit_radio_polynomial_null,
    fit_unregularized_common_affine_candidates,
    permute_fit_response_within_paths,
)


def _track() -> MeasurementTrack:
    time = np.tile(np.linspace(0.0, 1.0, 60), 4)
    path = np.repeat(np.arange(4), 60)
    radio = np.repeat(np.asarray([0, 0, 1, 1]), 60)
    orbit = -3_500.0 * time + 18.0 * time**2
    offsets = np.asarray([10_000.0, -8_000.0, 5_000.0, -12_000.0])[path]
    rates = np.asarray([35.0, -25.0])[radio] * (time - 0.5)
    measured = orbit + offsets + rates
    return MeasurementTrack(
        time_s=time,
        fit_cfo_hz=measured,
        response_cfo_hz=measured,
        path_index=path,
        radio_index=radio,
        path_ids=("p0", "p1", "p2", "p3"),
        radio_ids=("r0", "r1"),
    )


def test_hierarchical_fit_recovers_radio_departures_and_true_candidate() -> None:
    track = _track()
    true = -3_500.0 * track.time_s + 18.0 * track.time_s**2
    wrong = -3_000.0 * track.time_s - 60.0 * track.time_s**2
    predictions = np.vstack((true, wrong))
    train = chronological_mask(track.time_s, 0.6)
    evaluation = ~train

    fit = fit_hierarchical_candidates(
        track,
        predictions,
        train,
        evaluation,
        measurement_scale_hz=1.0,
        rate_prior_sigma_hz_s=1_000.0,
        maximum_rate_hz_s=150.0,
    )

    assert int(np.argmin(fit.penalized_training_rms_hz)) == 0
    assert fit.evaluation_rms_hz[0] < 0.1
    assert fit.radio_rate_departures_hz_s[0] == pytest.approx([35.0, -25.0], abs=0.1)
    affine = fit_unregularized_common_affine_candidates(
        track,
        predictions,
        train,
        evaluation,
    )
    assert affine.common_rate_departure_hz_s[0] == pytest.approx(5.0, abs=0.1)
    assert np.isfinite(affine.evaluation_rms_hz).all()
    future_fit_changed = replace(
        track,
        fit_cfo_hz=np.where(evaluation, track.fit_cfo_hz + 1_000_000.0, track.fit_cfo_hz),
    )
    affine_after_future_change = fit_unregularized_common_affine_candidates(
        future_fit_changed,
        predictions,
        train,
        evaluation,
    )
    assert affine_after_future_change.common_rate_departure_hz_s == pytest.approx(
        affine.common_rate_departure_hz_s
    )
    assert affine_after_future_change.path_offsets_hz == pytest.approx(affine.path_offsets_hz)


def test_offset_baseline_cannot_absorb_receiver_rate() -> None:
    track = _track()
    true = (-3_500.0 * track.time_s + 18.0 * track.time_s**2)[None, :]
    train = chronological_mask(track.time_s, 0.6)
    baseline = fit_offset_candidates(track, true, train, ~train)
    hierarchy = fit_hierarchical_candidates(
        track,
        true,
        train,
        ~train,
        measurement_scale_hz=1.0,
        rate_prior_sigma_hz_s=1_000.0,
        maximum_rate_hz_s=150.0,
    )
    assert hierarchy.evaluation_rms_hz[0] < baseline.evaluation_rms_hz[0]


def test_radio_polynomial_null_is_training_only_and_finite() -> None:
    track = _track()
    train = chronological_mask(track.time_s, 0.6)
    fit = fit_radio_polynomial_null(track, train, ~train, degree=2)
    assert fit.degree == 2
    assert len(fit.coefficients_hz) == 2
    assert np.isfinite(fit.evaluation_rms_hz)
    independent = fit_independent_path_linear_null(track, train, ~train)
    assert len(independent.path_rates_hz_s) == 4
    assert np.isfinite(independent.training_rms_hz)
    assert np.isfinite(independent.evaluation_rms_hz)
    future_fit_changed = replace(
        track,
        fit_cfo_hz=np.where(~train, track.fit_cfo_hz + 1_000_000.0, track.fit_cfo_hz),
    )
    independent_after_future_change = fit_independent_path_linear_null(
        future_fit_changed,
        train,
        ~train,
    )
    assert independent_after_future_change.path_offsets_hz == pytest.approx(
        independent.path_offsets_hz
    )
    assert independent_after_future_change.path_rates_hz_s == pytest.approx(
        independent.path_rates_hz_s
    )


def test_rolling_masks_and_permutation_are_path_local() -> None:
    track = _track()
    train = chronological_mask(track.time_s, 0.6)
    block = chronological_block_mask(track.time_s, 0.6, 0.7)
    assert not np.any(train & block)
    permuted = permute_fit_response_within_paths(track, train, np.random.default_rng(7))
    assert np.array_equal(permuted.fit_cfo_hz[~train], track.fit_cfo_hz[~train])
    for path in range(4):
        selected = train & (track.path_index == path)
        assert np.array_equal(
            np.sort(permuted.fit_cfo_hz[selected]),
            np.sort(track.fit_cfo_hz[selected]),
        )


@pytest.mark.parametrize("degree", [0, 3])
def test_unsupported_polynomial_null_degree_is_rejected(degree: int) -> None:
    track = _track()
    train = chronological_mask(track.time_s, 0.6)
    with pytest.raises(ValueError, match="one or two"):
        fit_radio_polynomial_null(track, train, ~train, degree=degree)
