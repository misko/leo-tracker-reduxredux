from __future__ import annotations

from dataclasses import replace

import numpy as np

from leo.analysis.research.v3_v4_downstream_rate import (
    V3V4ForecastConfig,
    V3V4SplitFrame,
    common_mode_forecasts,
    method_forecasts,
)


def _frames(*, cfo_offset_hz: float = 0.0) -> tuple[V3V4SplitFrame, ...]:
    output = []
    for ordinal in range(750):
        time_s = ordinal / 750.0
        even = 100_000.0 - 3_200.0 * time_s + cfo_offset_hz
        output.append(
            V3V4SplitFrame(
                frame_ordinal=ordinal,
                frame_start_sample=1_000 + round(ordinal * 2_500_000 / 750),
                reference_time_s=time_s,
                even_cfo_hz=even,
                odd_cfo_hz=even + 7.0,
                even_frequency_uncertainty_hz=25.0,
                even_exact_coherence=0.25,
                even_control_coherence=0.02,
                training_supported=True,
                even_search_boundary=False,
                odd_search_boundary=False,
            )
        )
    return tuple(output)


def test_fixed_500ms_forecast_recovers_linear_rate() -> None:
    predictions = method_forecasts(
        _frames(),
        method="v3",
        population="method_own",
        anchor_key="anchor",
    )
    fixed = tuple(item for item in predictions if item.history_ms == 500)

    assert len(fixed) == 15
    assert all(item.training_frame_count >= 300 for item in fixed)
    assert all(item.training_span_ms >= 450.0 for item in fixed)
    assert np.allclose([item.fitted_rate_hz_s for item in fixed], -3_200.0, atol=1e-6)
    assert np.allclose([item.odd_residual_hz for item in fixed], 7.0, atol=1e-6)


def test_odd_perturbation_cannot_change_mask_fit_or_prediction() -> None:
    original = _frames()
    perturbed = tuple(replace(item, odd_cfo_hz=item.odd_cfo_hz + 50_000.0) for item in original)
    left = method_forecasts(
        original,
        method="v3",
        population="method_own",
        anchor_key="anchor",
    )
    right = method_forecasts(
        perturbed,
        method="v3",
        population="method_own",
        anchor_key="anchor",
    )

    fit_fields = (
        "target_offset_ms",
        "target_ordinal",
        "history_ms",
        "training_frame_count",
        "training_first_ordinal",
        "training_last_ordinal",
        "fitted_cfo_hz",
        "fitted_rate_hz_s",
        "predicted_cfo_hz",
    )
    assert [tuple(getattr(item, field) for field in fit_fields) for item in left] == [
        tuple(getattr(item, field) for field in fit_fields) for item in right
    ]
    assert np.allclose(
        [
            right_item.odd_residual_hz - left_item.odd_residual_hz
            for left_item, right_item in zip(left, right, strict=True)
        ],
        50_000.0,
    )


def test_common_mode_uses_identical_even_supported_ordinals() -> None:
    left = _frames()
    right = tuple(
        replace(
            item,
            even_cfo_hz=item.even_cfo_hz + 100.0,
            odd_cfo_hz=item.odd_cfo_hz + 100.0,
            training_supported=item.frame_ordinal % 17 != 0,
        )
        for item in _frames(cfo_offset_hz=100.0)
    )
    predictions = common_mode_forecasts(
        left,
        right,
        left_method="v3",
        right_method="v4",
        anchor_key="anchor",
    )

    assert predictions
    by_key: dict[tuple[int, int], list[object]] = {}
    for item in predictions:
        by_key.setdefault((item.target_offset_ms, item.history_ms), []).append(item)
    assert all(len(pair) == 2 for pair in by_key.values())
    assert all(
        pair[0].training_frame_count == pair[1].training_frame_count for pair in by_key.values()
    )
    assert all(
        pair[0].training_first_ordinal == pair[1].training_first_ordinal for pair in by_key.values()
    )
    assert all(
        pair[0].training_last_ordinal == pair[1].training_last_ordinal for pair in by_key.values()
    )


def test_support_gate_preserves_an_insufficient_fixed_500ms_failure() -> None:
    sparse = tuple(
        replace(item, training_supported=item.frame_ordinal % 2 == 0) for item in _frames()
    )
    predictions = method_forecasts(
        sparse,
        method="v3",
        population="method_own",
        anchor_key="anchor",
        config=V3V4ForecastConfig(),
    )

    assert all(item.history_ms == 20 for item in predictions)
