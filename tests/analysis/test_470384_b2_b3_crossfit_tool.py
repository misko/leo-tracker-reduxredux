from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np


def _tool() -> ModuleType:
    tools_root = Path(__file__).parents[2] / "tools"
    sys.path.insert(0, str(tools_root))
    path = tools_root / "report_470384_b2_b3_crossfit.py"
    spec = importlib.util.spec_from_file_location("report_470384_b2_b3_crossfit_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _profile(tool: ModuleType, frequency_hz: float):
    symbol_times = np.arange(64, dtype=float) * 4.4e-6
    times = np.stack([symbol_times + frame * 1.333e-3 for frame in range(10)])
    phases = np.linspace(-1.9, 2.2, len(times))
    centered = times - np.mean(times, axis=1, keepdims=True)
    values = np.exp(1j * (phases[:, None] + 2 * np.pi * frequency_hz * centered))
    return tool.continuous.ProfileLikelihood.from_correlations(values, times)


def test_vector_profile_scores_match_scalar_evaluation() -> None:
    tool = _tool()
    profile = _profile(tool, 7_843.2)
    frequencies = np.asarray([-12_000.0, 0.0, 7_843.2, 19_000.0])

    vector = tool._profile_scores(profile, frequencies)
    scalar = np.asarray([profile.score(item) for item in frequencies])

    assert np.allclose(vector, scalar, rtol=1e-13, atol=1e-14)


def test_global_audit_recovers_peak_far_from_an_unrelated_local_seed() -> None:
    tool = _tool()
    true_frequency_hz = 18_713.4
    profile = _profile(tool, true_frequency_hz)

    result, grid, scores = tool.global_continuous_maximum(
        profile,
        symbol_step_s=4.4e-6,
    )

    assert len(grid) == tool.continuous.GLRT_SIZE
    assert scores.shape == grid.shape
    assert abs(result.frequency_hz - true_frequency_hz) < 1e-3
    assert np.isclose(result.score, 1.0, rtol=0.0, atol=1e-12)
