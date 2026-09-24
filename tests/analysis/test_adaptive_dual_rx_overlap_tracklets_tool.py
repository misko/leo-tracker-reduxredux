from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

TOOLS = Path(__file__).parents[2] / "tools"
sys.path.insert(0, str(TOOLS))
PATH = TOOLS / "report_adaptive_dual_rx_overlap_tracklets.py"
SPEC = importlib.util.spec_from_file_location("overlap_tracklets_tool", PATH)
assert SPEC is not None and SPEC.loader is not None
tool = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = tool
SPEC.loader.exec_module(tool)


def _observation(*, phase_rad: float = 0.7, noise_rad: float = 0.0) -> SimpleNamespace:
    rate = 2_500_000.0
    offset_hz = -676_500.0
    residual_hz = 1_125.0
    starts = np.arange(19) * round(rate / 750) + 20_000
    center = float(np.mean(starts))
    rng = np.random.default_rng(8)
    perturbation = rng.normal(scale=noise_rad, size=len(starts))
    product = np.exp(
        1j * (phase_rad + 2 * np.pi * residual_hz * (starts - center) / rate + perturbation)
    )
    receiver0 = SimpleNamespace(
        frame_starts=tuple(map(int, starts)), frame_phasors=tuple(np.ones(len(starts)))
    )
    receiver1 = SimpleNamespace(frame_starts=tuple(map(int, starts)), frame_phasors=tuple(product))
    return SimpleNamespace(
        receivers=(receiver0, receiver1),
        center_sample=center,
        relative_frequency_hz=offset_hz + residual_hz,
        wrapped_phase_rad=phase_rad,
    )


def test_frame_subsets_share_one_reference_and_preserve_full_cycle_phase() -> None:
    observation = _observation()
    first = tool.phase_subset_at_reference(observation, -676_500.0, 2_500_000.0, np.arange(0, 9))
    second = tool.phase_subset_at_reference(observation, -676_500.0, 2_500_000.0, np.arange(9, 19))

    assert first == pytest.approx(0.7, abs=1e-10)
    assert second == pytest.approx(0.7, abs=1e-10)


def test_moving_block_bootstrap_reports_conditional_frame_uncertainty() -> None:
    exact = tool.block_bootstrap_phase(
        _observation(), -676_500.0, 2_500_000.0, seed=1, replicates=200
    )
    noisy = tool.block_bootstrap_phase(
        _observation(noise_rad=0.2), -676_500.0, 2_500_000.0, seed=1, replicates=200
    )

    assert exact["block_frames"] == 3
    assert exact["conditional_standard_error_deg"] < 1e-8
    assert noisy["conditional_standard_error_deg"] > 1.0
    assert noisy["conditional_95_interval_low_deg"] < 0
    assert noisy["conditional_95_interval_high_deg"] > 0
