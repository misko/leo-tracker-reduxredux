from __future__ import annotations

import numpy as np
import pytest

from leo.analysis.research.multi_radio_common_rate import (
    MultiRadioFramePoint,
    block_bootstrap_radio_rate_sigma,
    block_bootstrap_rate_sigma,
    common_rate_prediction_metrics,
    fit_common_rate,
    fit_radio_rates,
    fit_separate_path_rates,
    fixed_history_causal_predictions,
    prediction_metrics_from_causal,
    radio_rate_prediction_metrics,
    separate_rate_prediction_metrics,
)


def _points(
    *,
    rates: tuple[float, float] = (-3_500.0, -3_500.0),
    odd_shift_hz: float = 0.0,
) -> tuple[MultiRadioFramePoint, ...]:
    generator = np.random.default_rng(1428)
    output = []
    for path_index, (path_id, radio_id, offset, rate) in enumerate(
        (
            ("stream-0/radio_pluto_5d4d/RX0", "radio_pluto_5d4d", 120_000.0, rates[0]),
            ("stream-1/radio_pluto_19f2/RX1", "radio_pluto_19f2", -180_000.0, rates[1]),
        )
    ):
        for index, time_s in enumerate(np.arange(0.0, 1.0, 0.01)):
            noise = float(generator.normal(0.0, 8.0))
            if path_index == 1 and index == 31:
                noise += 600.0
            even = offset + rate * time_s + noise
            odd = offset + rate * time_s + float(generator.normal(0.0, 9.0)) + odd_shift_hz
            output.append(
                MultiRadioFramePoint(
                    point_id=f"p{path_index}-{index}",
                    path_id=path_id,
                    physical_radio_id=radio_id,
                    time_s=float(time_s),
                    even_cfo_hz=even,
                    odd_cfo_hz=odd,
                    even_sigma_hz=12.0,
                )
            )
    return tuple(output)


def test_common_rate_recovers_shared_slope_with_free_offsets_and_outlier() -> None:
    points = _points()
    train = tuple(point for point in points if point.time_s < 0.6)
    heldout = tuple(point for point in points if point.time_s >= 0.6)

    shared = fit_common_rate(train)
    separate = fit_separate_path_rates(train)
    shared_metrics = common_rate_prediction_metrics(shared, heldout)
    separate_metrics = separate_rate_prediction_metrics(separate, heldout)

    assert shared.rate_hz_s == pytest.approx(-3_500.0, abs=10.0)
    assert {item.path_id for item in separate} == {point.path_id for point in points}
    assert shared.path_count == 2
    assert shared.odd_symbols_influenced_fit is False
    assert shared.per_path_drift_fitted is False
    assert shared_metrics.rms_hz < 15.0
    assert separate_metrics.rms_hz < 16.0


def test_separate_rates_expose_disagreement_that_common_model_cannot_hide() -> None:
    points = _points(rates=(-3_300.0, -3_700.0))
    fits = fit_separate_path_rates(points)
    by_path = {fit.physical_radio_id: fit.rate_hz_s for fit in fits}
    shared = fit_common_rate(points)

    assert by_path["radio_pluto_5d4d"] == pytest.approx(-3_300.0, abs=10.0)
    assert by_path["radio_pluto_19f2"] == pytest.approx(-3_700.0, abs=10.0)
    assert shared.rate_hz_s == pytest.approx(-3_500.0, abs=10.0)


def test_radio_rates_pool_paths_with_free_intercepts() -> None:
    points = _points(rates=(-3_300.0, -3_700.0))
    extra_path = tuple(
        MultiRadioFramePoint(
            point_id=f"extra-{point.point_id}",
            path_id="stream-0/radio_pluto_5d4d/RX1",
            physical_radio_id=point.physical_radio_id,
            time_s=point.time_s,
            even_cfo_hz=point.even_cfo_hz + 50_000.0,
            odd_cfo_hz=(point.odd_cfo_hz + 50_000.0 if point.odd_cfo_hz is not None else None),
            even_sigma_hz=point.even_sigma_hz,
        )
        for point in points
        if point.physical_radio_id == "radio_pluto_5d4d"
    )
    combined = (*points, *extra_path)

    fits = fit_radio_rates(combined)
    by_radio = {fit.physical_radio_id: fit for fit in fits}

    assert by_radio["radio_pluto_5d4d"].path_count == 2
    assert by_radio["radio_pluto_5d4d"].rate_hz_s == pytest.approx(-3_300.0, abs=10.0)
    assert by_radio["radio_pluto_19f2"].rate_hz_s == pytest.approx(-3_700.0, abs=10.0)
    assert radio_rate_prediction_metrics(fits, combined).rms_hz < 16.0
    sigma = block_bootstrap_radio_rate_sigma(
        tuple(point for point in combined if point.physical_radio_id == "radio_pluto_5d4d"),
        replicates=40,
    )
    assert 0.0 < sigma < 100.0


def test_odd_qin_perturbation_cannot_change_fit_or_bootstrap() -> None:
    clean = _points()
    poisoned = _points(odd_shift_hz=50_000.0)

    assert fit_common_rate(clean).rate_hz_s == fit_common_rate(poisoned).rate_hz_s
    assert [fit.rate_hz_s for fit in fit_separate_path_rates(clean)] == [
        fit.rate_hz_s for fit in fit_separate_path_rates(poisoned)
    ]
    assert block_bootstrap_rate_sigma(clean, shared=True, replicates=40) == (
        block_bootstrap_rate_sigma(poisoned, shared=True, replicates=40)
    )


def test_causal_fixed_history_is_strictly_past_only_and_prefix_invariant() -> None:
    points = _points()
    targets = tuple(point for point in points if point.time_s >= 0.6)
    baseline = fixed_history_causal_predictions(points, targets)
    poisoned = tuple(
        MultiRadioFramePoint(
            point_id=point.point_id,
            path_id=point.path_id,
            physical_radio_id=point.physical_radio_id,
            time_s=point.time_s,
            even_cfo_hz=point.even_cfo_hz + (100_000.0 if point.time_s >= 0.8 else 0.0),
            odd_cfo_hz=point.odd_cfo_hz,
            even_sigma_hz=point.even_sigma_hz,
        )
        for point in points
    )
    poisoned_predictions = fixed_history_causal_predictions(poisoned, targets)
    baseline_prefix = [item for item in baseline if item.time_s <= 0.8]
    poisoned_prefix = [item for item in poisoned_predictions if item.time_s <= 0.8]

    assert baseline_prefix == poisoned_prefix
    assert all(item.history_stop_s < item.time_s for item in baseline)
    assert prediction_metrics_from_causal(baseline).rms_hz < 20.0


def test_bootstrap_is_deterministic_and_positive() -> None:
    points = _points()
    first = block_bootstrap_rate_sigma(points, shared=True, replicates=40, seed=123)
    second = block_bootstrap_rate_sigma(points, shared=True, replicates=40, seed=123)

    assert first == second
    assert 0.0 < first < 100.0


def test_invalid_point_identity_and_single_path_common_fit_fail_closed() -> None:
    points = _points()
    duplicate = (*points[:3], points[0])
    one_path = tuple(point for point in points if point.physical_radio_id == "radio_pluto_5d4d")

    with pytest.raises(ValueError, match="unique"):
        fit_common_rate(duplicate)
    with pytest.raises(ValueError, match="path count"):
        fit_common_rate(one_path)
