from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest


def _tool() -> ModuleType:
    path = Path(__file__).parents[2] / "tools" / "report_adaptive_dual_rx_phase.py"
    spec = importlib.util.spec_from_file_location("adaptive_dual_rx_phase_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _hypothesis(
    visit: int,
    time_s: float,
    frequencies_hz: tuple[float, float],
    phase_deg: float,
) -> dict:
    return {
        "visit_index": visit,
        "target_index": 0,
        "acquisition_time_s": time_s,
        "signal_frequencies_hz": list(frequencies_hz),
        "signal_separation_hz": abs(frequencies_hz[1] - frequencies_hz[0]),
        "double_difference_deg": phase_deg,
        "double_relative_frequency_hz": 0.1,
        "quality_floor": 0.9,
    }


def test_association_connects_signal_order_reversal_at_alias_boundary() -> None:
    tool = _tool()
    alias_hz = tool.SYMBOL_ALIAS_HZ
    document = {
        "hypotheses": [
            _hypothesis(index, float(index), (-112_000 + index * 500, -82_000 + index * 500), 0)
            for index in range(3)
        ]
        + [
            _hypothesis(
                3,
                3.0,
                (-80_500, -110_500 + alias_hz),
                0,
            )
        ]
    }
    document["hypotheses"][-1]["signal_separation_hz"] = 30_000

    paths = tool.associate(document)

    assert len(paths) == 1
    assert len(paths[0]) == 4
    orientations = [state.orientation for state in paths[0]]
    assert orientations[:3] == [orientations[0]] * 3
    assert orientations[3] != orientations[0]


def test_association_is_unchanged_when_phase_is_randomized() -> None:
    tool = _tool()
    hypotheses = [
        _hypothesis(index, float(index), (-50_000 - 500 * index, -20_000 - 400 * index), 0)
        for index in range(6)
    ]
    original = {"hypotheses": hypotheses}
    randomized = {
        "hypotheses": [
            {**row, "double_difference_deg": phase}
            for row, phase in zip(hypotheses, (170, -80, 25, 100, -160, 45), strict=True)
        ]
    }

    original_path = tool.associate(original)[0]
    randomized_path = tool.associate(randomized)[0]

    def identity(path):
        return [(state.hypothesis_id, state.orientation) for state in path]

    assert identity(original_path) == identity(randomized_path)


def test_association_prefers_pilot_quality_over_phase_quality() -> None:
    tool = _tool()
    hypotheses = [
        {
            **_hypothesis(
                index,
                float(index),
                (-50_000 - 500 * index, -20_000 - 400 * index),
                15 * index,
            ),
            "association_quality_floor": 3.0,
            "quality_floor": 0.2,
        }
        for index in range(4)
    ]

    path = tool.associate({"hypotheses": hypotheses})[0]

    assert len(path) == 4
    assert all(state.quality == pytest.approx(3.0) for state in path)


def test_phase_metrics_recover_a_linear_track_after_association() -> None:
    tool = _tool()
    states = [
        tool.AssociationState(
            hypothesis_id=index,
            orientation=0,
            visit_index=index,
            target_index=0,
            time_s=float(index),
            frequencies_hz=(-50_000 - index, -20_000 - index),
            separation_hz=30_000,
            phase_deg=20 + 24 * index,
            phase_rate_hz=24 / 360,
            quality=0.9,
        )
        for index in range(7)
    ]

    metrics = tool.phase_metrics(states, np.random.default_rng(7))

    assert metrics["linear_slope_deg_s"] == pytest.approx(24.0)
    assert metrics["linear_residual_rms_deg"] == pytest.approx(0.0, abs=1e-10)
    assert metrics["increment_concentration"] == pytest.approx(1.0)
    assert metrics["median_abs_rate_prediction_error_deg"] == pytest.approx(
        0.0, abs=1e-10
    )


def test_phase_restoration_counts_individual_residual_cfo_once() -> None:
    tool = _tool()
    sample_rate_hz = 2_500_000.0
    references = (1_000_000, 1_000_004)
    center_sample = 1_060_000.0
    acquired = (-80_000.0, -700_000.0)
    residuals = (123.0, -87.0)
    reference_phase_rad = 0.37
    # The coherent frame product already contains each individual residual's
    # propagation from its receiver reference to the common center.
    product_phase_at_center = reference_phase_rad + 2 * np.pi * (
        residuals[1] * (center_sample - references[1])
        - residuals[0] * (center_sample - references[0])
    ) / sample_rate_hz
    expected = reference_phase_rad + 2 * np.pi * (
        (acquired[1] + residuals[1]) * (center_sample - references[1])
        - (acquired[0] + residuals[0]) * (center_sample - references[0])
    ) / sample_rate_hz

    observed = tool.restore_receiver_relative_phase(
        product_phase_at_center,
        acquired,
        center_sample,
        references,
        sample_rate_hz,
    )

    assert np.angle(np.exp(1j * (observed - expected))) == pytest.approx(0.0, abs=1e-10)


def test_relative_frequency_uses_product_residual_only_once() -> None:
    tool = _tool()

    observed = tool.receiver_relative_frequency_hz((-80_000.0, -700_000.0), -210.0)

    assert observed == pytest.approx(-620_210.0)


def test_pairing_uses_common_receiver_offset_instead_of_fixed_prior() -> None:
    tool = _tool()
    edges = [
        # Three true pairs share an offset near -642 kHz, outside the old
        # fixed 20 kHz window around -620 kHz.
        (0, 0, -642_100.0, 0.9),
        (1, 1, -641_800.0, 0.8),
        (2, 2, -642_400.0, 0.7),
        # Strong but mutually inconsistent cross-pairing distractors.
        (0, 1, -570_000.0, 1.0),
        (1, 2, -520_000.0, 1.0),
        (2, 0, -680_000.0, 1.0),
    ]

    selected = tool.select_consistent_receiver_pairs(edges)

    assert {(edge[0], edge[1]) for edge in selected} == {(0, 0), (1, 1), (2, 2)}


def test_simultaneous_double_difference_cancels_common_phase_motion() -> None:
    tool = _tool()
    common_phase = np.linspace(-7.0, 11.0, 23)
    low_geometry = 0.3
    expected_difference = -0.72
    low = np.exp(1j * (common_phase + low_geometry))
    high = np.exp(1j * (common_phase + low_geometry + expected_difference))

    observed, concentration = tool.simultaneous_double_difference(
        low,
        high,
        np.linspace(0.2, 1.0, len(low)),
    )

    assert observed == pytest.approx(expected_difference)
    assert concentration == pytest.approx(1.0)


def test_circular_phase_uncertainty_improves_with_support() -> None:
    tool = _tool()

    short = tool.circular_phase_standard_error_deg(0.95, 6)
    long = tool.circular_phase_standard_error_deg(0.95, 24)
    more_coherent = tool.circular_phase_standard_error_deg(0.99, 6)

    assert long == pytest.approx(short / 2)
    assert more_coherent < short
