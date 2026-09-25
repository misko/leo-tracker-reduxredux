from __future__ import annotations

import pytest

from leo.analysis.research.ramp_tle_association import (
    CandidateRateSeries,
    RampRateAssociationConfig,
    RampRateSeries,
    associate_ramp_rates,
)


def _candidate(number: int, values: tuple[float, ...]) -> CandidateRateSeries:
    return CandidateRateSeries(
        object_name=f"STARLINK-{number}",
        catalog_number=number,
        predicted_rate_hz_s=values,
        peak_elevation_deg=80.0,
        minimum_elevation_deg=70.0,
        element_epoch_utc_ns=1_000_000_000,
        element_age_s=3_600.0,
    )


def test_ramp_rate_match_ignores_bounded_constant_drift_and_holds_out_tail() -> None:
    times = tuple(float(index) for index in range(10))
    truth = tuple(-3_000.0 - 10.0 * index - 0.5 * index**2 for index in range(10))
    observed = RampRateSeries(
        time_s=times,
        rate_hz_s=tuple(value + 125.0 for value in truth),
        sigma_hz_s=(25.0,) * 10,
    )
    wrong = tuple(-3_000.0 + 20.0 * index for index in range(10))

    result = associate_ramp_rates(observed, (_candidate(2, wrong), _candidate(1, truth)))

    assert result.candidate_count == 2
    assert result.ranked[0].candidate.catalog_number == 1
    assert result.ranked[0].metrics.fitted_rate_nuisance_hz_s == pytest.approx(125.0)
    assert result.ranked[0].metrics.train_rms_hz_s == pytest.approx(0.0, abs=1e-9)
    assert result.ranked[0].metrics.holdout_rms_hz_s == pytest.approx(0.0, abs=1e-9)
    assert result.training_indices == (0, 1, 2, 3, 4, 5)
    assert result.holdout_indices == (6, 7, 8, 9)


def test_ramp_rate_match_exposes_nuisance_bound_and_train_only_ranking() -> None:
    observed = RampRateSeries(
        time_s=(0.0, 1.0, 2.0, 3.0, 4.0),
        rate_hz_s=(0.0, 0.0, 0.0, 1_000.0, 1_000.0),
        sigma_hz_s=(10.0,) * 5,
    )
    first = _candidate(10, (500.0, 500.0, 500.0, 1_000.0, 1_000.0))
    second = _candidate(20, (0.0, 0.0, 0.0, 0.0, 0.0))

    result = associate_ramp_rates(
        observed,
        (first, second),
        RampRateAssociationConfig(nuisance_rate_bound_hz_s=200.0),
    )

    # The first candidate would look attractive on the tail, but selection is
    # made entirely on the first three chronological ramps.
    assert result.ranked[0].candidate.catalog_number == 20
    first_result = next(item for item in result.ranked if item.candidate.catalog_number == 10)
    assert first_result.metrics.nuisance_at_bound is True
    assert first_result.metrics.fitted_rate_nuisance_hz_s == pytest.approx(-200.0)


def test_ramp_rate_match_rejects_candidate_length_mismatch() -> None:
    observed = RampRateSeries(
        time_s=(0.0, 1.0, 2.0, 3.0, 4.0),
        rate_hz_s=(0.0,) * 5,
        sigma_hz_s=(10.0,) * 5,
    )

    with pytest.raises(ValueError, match="candidate rate count"):
        associate_ramp_rates(observed, (_candidate(1, (0.0,) * 6),))
