from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np


def _tool():
    path = Path(__file__).parents[2] / "tools" / "replay_aug22_pnt_kalman_same_mask.py"
    spec = importlib.util.spec_from_file_location("replay_aug22_same_mask", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_same_mask_is_causal_post_bootstrap_and_block_equal() -> None:
    tool = _tool()
    frames = []
    for index in range(25):
        time_s = index / 750.0
        measurement = 100_000.0 - 2_000.0 * time_s + 4.0 * (-1) ** index
        frames.append(
            SimpleNamespace(
                measurement_supported=True,
                time_s=time_s,
                absolute_cfo_measurement_hz=measurement,
                frequency_innovation_hz=2.0,
            )
        )
    case = SimpleNamespace(detection_time_s=1.2)
    result = SimpleNamespace(frames=tuple(frames))

    evidence = tool.same_mask([(case, result)])

    assert evidence["status"] == "estimable"
    assert evidence["common_frame_count"] == 13
    assert evidence["recording_anchored_one_second_block_count"] == 1
    assert evidence["kalman_block_equal_rms_hz"] == 2.0
    assert np.isfinite(evidence["kalman_to_trailing_20ms_rms_ratio"])


def test_robust_line_recovers_an_uncontaminated_linear_ramp() -> None:
    tool = _tool()
    time_s = np.linspace(0.0, 0.02, 16)
    cfo_hz = 80_000.0 - 3_000.0 * time_s

    reference, coefficients = tool.robust_line(time_s, cfo_hz)

    assert reference == np.median(time_s)
    np.testing.assert_allclose(coefficients[1], -3_000.0)


def test_filter_case_allows_an_empty_fail_closed_result() -> None:
    tool = _tool()
    reader = SimpleNamespace(
        sample_rate_hz=100.0,
        read=lambda start, count, receiver_ids: np.zeros((count, 1, 2), dtype=np.int16),
    )
    case = SimpleNamespace(
        sample_start=0,
        receiver=1,
        local_epoch_sample=0,
        initial_cfo_hz=0.0,
        edge="lower",
    )
    empty = SimpleNamespace(frames=(), supported_frame_count=0, phase_lock_qualified=False)
    calls = []

    def analyzer(samples, sample_rate_hz, **kwargs):
        calls.append((samples.shape, sample_rate_hz, kwargs))
        return empty

    result = tool.analyze_filter_case(reader, case, analyzer)

    assert result.exact is empty
    assert result.rolled is empty
    assert len(calls) == 2
    assert calls[1][2]["expected_symbol_roll"] == tool.CONTROL_SYMBOL_ROLL
