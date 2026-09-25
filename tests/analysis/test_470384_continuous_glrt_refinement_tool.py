from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import numpy as np


def _tool() -> ModuleType:
    tools_root = Path(__file__).parents[2] / "tools"
    sys.path.insert(0, str(tools_root))
    path = tools_root / "report_470384_continuous_glrt_refinement.py"
    spec = importlib.util.spec_from_file_location(
        "report_470384_continuous_glrt_refinement_tool", path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _profile(tool: ModuleType, residual_hz: float):
    symbol_times = np.arange(64, dtype=float) * 4.4e-6
    times = np.stack([symbol_times + frame * 1.333e-3 for frame in range(12)])
    frame_phases = np.linspace(-2.1, 2.4, len(times))
    centered = times - np.mean(times, axis=1, keepdims=True)
    values = np.exp(1j * (frame_phases[:, None] + 2 * np.pi * residual_hz * centered))
    return tool.ProfileLikelihood.from_correlations(values, times)


def test_profile_analytic_derivatives_match_finite_differences() -> None:
    tool = _tool()
    profile = _profile(tool, 713.4)
    frequency_hz = 650.0
    step_hz = 0.1

    value, gradient, hessian = profile.value_gradient_hessian(frequency_hz)
    leading = profile.score(frequency_hz - step_hz)
    trailing = profile.score(frequency_hz + step_hz)
    finite_gradient = (trailing - leading) / (2 * step_hz)
    finite_hessian = (trailing - 2 * value + leading) / step_hz**2

    assert np.isclose(gradient, finite_gradient, rtol=2e-6, atol=1e-12)
    assert np.isclose(hessian, finite_hessian, rtol=2e-5, atol=1e-12)


def test_bracketed_newton_recovers_sub_bin_frequency_and_increases_score() -> None:
    tool = _tool()
    true_frequency_hz = 713.4
    profile = _profile(tool, true_frequency_hz)
    discrete_frequency_hz = 666.0
    discrete_score = profile.score(discrete_frequency_hz)

    result = tool.maximize_profile_likelihood(
        profile,
        initial_frequency_hz=discrete_frequency_hz,
        half_width_hz=220.0,
    )

    assert result.method == "bracketed-newton"
    assert abs(result.frequency_hz - true_frequency_hz) < 1e-3
    assert result.score > discrete_score
    assert result.hessian < 0.0
    assert not result.at_boundary


def test_golden_fallback_remains_bounded() -> None:
    tool = _tool()
    profile = _profile(tool, 713.4)

    result = tool.maximize_profile_likelihood(
        profile,
        initial_frequency_hz=-2_000.0,
        half_width_hz=100.0,
    )

    assert result.method == "golden-section"
    assert -2_100.0 <= result.frequency_hz <= -1_900.0


def test_cfo_time_comparison_renders_original_refined_and_difference(tmp_path: Path) -> None:
    tool = _tool()
    rows = (
        SimpleNamespace(
            branch_index=0,
            time_s=31.0,
            persisted_tracking_cfo_hz=250_000.0,
            continuous_tracking_cfo_hz=250_075.0,
            cfo_correction_hz=75.0,
        ),
        SimpleNamespace(
            branch_index=0,
            time_s=31.02,
            persisted_tracking_cfo_hz=249_900.0,
            continuous_tracking_cfo_hz=249_850.0,
            cfo_correction_hz=-50.0,
        ),
    )
    path = tmp_path / "cfo-time.png"

    tool.render_cfo_time_comparison(
        path,
        rows=rows,
        summaries=({"branch_index": 0, "branch_label": "B1 · synthetic"},),
    )

    assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
