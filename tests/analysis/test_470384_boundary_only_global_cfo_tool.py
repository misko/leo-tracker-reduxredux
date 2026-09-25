from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest


def _tool() -> ModuleType:
    tools_root = Path(__file__).parents[2] / "tools"
    sys.path.insert(0, str(tools_root))
    path = tools_root / "report_470384_boundary_only_global_cfo.py"
    spec = importlib.util.spec_from_file_location(
        "report_470384_boundary_only_global_cfo_tool",
        path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_boundary_manifest_rejects_window_measurements() -> None:
    tool = _tool()
    manifest = {
        "schema_version": 1,
        "session_id": tool.semicoherent.SESSION_ID,
        "stream_id": "stream-0",
        "receiver_id": 0,
        "sample_rate_hz": tool.semicoherent.SAMPLE_RATE_HZ,
        "frame_start_samples": [100, 200],
        "window_cfo_hz": 420_000.0,
    }

    with pytest.raises(ValueError, match="forbidden metadata"):
        tool.validate_boundary_manifest(manifest)


def test_line_scorer_recovers_synthetic_global_trajectory() -> None:
    tool = _tool()
    times = np.linspace(34.0, 36.0, 80)
    reference = float(np.mean(times))
    frequencies = np.arange(390_000.0, 450_000.1, 100.0)
    expected_frequency = 421_300.0
    expected_slope = -4_200.0
    likelihoods = np.stack(
        [
            np.exp(
                -0.5
                * (
                    (frequencies - (expected_frequency + expected_slope * (time - reference)))
                    / 120.0
                )
                ** 2
            )
            for time in times
        ]
    )
    candidates = np.asarray(
        [
            [expected_frequency, expected_slope],
            [expected_frequency + 1_000.0, expected_slope],
            [expected_frequency, expected_slope + 1_000.0],
        ]
    )

    scores = tool.score_lines(
        likelihoods,
        times,
        frequencies,
        reference_time_s=reference,
        parameters=candidates,
    )

    assert int(np.argmax(scores)) == 0
