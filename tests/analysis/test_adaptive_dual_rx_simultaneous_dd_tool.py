from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np


def _module() -> Any:
    path = Path("tools/report_adaptive_dual_rx_simultaneous_dd.py")
    spec = importlib.util.spec_from_file_location("_simultaneous_dd", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_exact_time_difference_cancels_shared_phase_trajectory() -> None:
    module = _module()
    rate = 1_000_000.0
    count = module.ATOM_SAMPLES
    samples = np.arange(count, dtype=float)
    bin_hz = rate / count
    centers = (300 * bin_hz, 400 * bin_hz)
    low_envelope = 0.7 + 0.3 * samples / (count - 1)
    high_envelope = 1.0 - 0.4 * samples / (count - 1)
    low = low_envelope * np.exp(2j * np.pi * centers[0] * samples / rate)
    high = high_envelope * np.exp(2j * np.pi * centers[1] * samples / rate)
    low_phase = math.radians(23.0)
    high_phase = math.radians(-41.0)
    shared = 0.7 * np.sin(2 * np.pi * samples / count) + 0.35 * (samples / count) ** 2
    rx0 = low + high
    rx1 = np.exp(1j * shared) * (
        low * np.exp(1j * low_phase) + high * np.exp(1j * high_phase)
    )
    atom = module.simultaneous_atom(
        np.column_stack((rx0, rx1)),
        rate,
        0.0,
        centers,
        global_start_sample=0,
    )
    measured = math.degrees(float(np.angle(atom.numerator)))
    expected = math.degrees(high_phase - low_phase)
    assert module._wrapped_difference_deg(measured, expected) == pytest.approx(0.0, abs=0.5)


def test_paired_bootstrap_is_zero_for_constant_double_difference() -> None:
    module = _module()
    phase = math.radians(17.0)
    blocks = [
        [
            module.MatchedAtom(np.exp(1j * phase), 1.0, index, index, index)
            for index in range(6)
        ]
        for _ in range(2)
    ]
    result = module.paired_moving_block_bootstrap(blocks, replicates=500, seed=3)
    assert result["conditional_standard_error_deg"] < 1e-10


def test_time_partition_reports_wrapped_difference() -> None:
    module = _module()
    phases = [10.0, 10.0, 10.0, 30.0, 30.0, 30.0]
    atoms = [
        module.MatchedAtom(np.exp(1j * math.radians(phase)), 1.0, index, index, index)
        for index, phase in enumerate(phases)
    ]
    result = module.summarize_atoms([atoms], 1_000_000.0)
    assert result["second_minus_first_deg"] == pytest.approx(20.0)


import pytest  # noqa: E402
