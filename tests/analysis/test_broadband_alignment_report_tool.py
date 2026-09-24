from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

TOOLS = Path(__file__).parents[2] / "tools"
sys.path.insert(0, str(TOOLS))
SPEC = importlib.util.spec_from_file_location(
    "broadband_report", TOOLS / "report_broadband_alignment.py"
)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_independent_generator_recovers_total_not_double_counted_delay():
    iq, rate, truth = module.make_case()
    result = module.estimate_broadband_alignment(
        iq,
        rate,
        receiver_cfo_seed_hz=truth["cfo_at_visit_start_hz"],
        cfo_search_half_width_hz=2000,
    )
    model = result.model
    expected_frequency = truth["cfo_at_visit_start_hz"] + truth["cfo_rate_hz_s"] * (
        model.reference_sample / rate
    )
    assert model.fractional_delay_samples == pytest.approx(2.375, abs=0.04)
    assert model.relative_cfo_hz == pytest.approx(expected_frequency, abs=1)
    assert model.relative_cfo_rate_hz_s == pytest.approx(480, abs=20)
    assert 0 < model.fractional_delay_standard_error_samples < 0.1
    time = model.reference_sample / rate
    phase_truth = (
        truth["phase_at_visit_start_rad"]
        + 2 * np.pi * (truth["cfo_at_visit_start_hz"] * time + truth["cfo_rate_hz_s"] * time**2 / 2)
        - 2 * np.pi * model.frequency_reference_hz * truth["rx1_delay_samples"] / rate
    )
    phase_error = np.angle(np.exp(1j * (model.phase_rad - phase_truth)))
    assert abs(np.degrees(phase_error)) < 1
    assert result.held_out.corrected_coherence > 0.85
    assert abs(result.held_out.corrected_cross_phase_rad) < 0.15


def test_serialization_retains_complex_components_and_rejects_nan_json():
    value = module.serializable({"h": np.array([1 + 2j]), "bad": np.float64(np.nan)})
    assert value == {"h": [{"real": 1.0, "imag": 2.0}], "bad": None}
