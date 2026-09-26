from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parents[2]
PATH = ROOT / "reports/2026_09_26_scan_fw_32a202b6e55630ec_phase_replay/dual-rx/analysis.py"
SPEC = importlib.util.spec_from_file_location("scan_dual_rx", PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _runner():
    path = PATH.parent / "run_corrected_direct.py"
    spec = importlib.util.spec_from_file_location("scan_dual_rx_runner", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_direct_phasor_restores_known_relative_cfo_and_phase() -> None:
    rate = 10_000
    count = 10_000
    time_s = np.arange(count) / rate
    phase = 0.73
    cfo = 17.0
    iq = np.empty((count, 2), dtype=np.complex64)
    iq[:, 0] = 1
    iq[:, 1] = np.exp(1j * (phase + 2 * np.pi * cfo * time_s))
    result = MODULE.direct_window_phasors(
        iq,
        np.ones((count, 2), dtype=np.bool_),
        device_counter_start=9_007_199_254_740_992,
        sample_rate_hz=rate,
        starts=np.arange(0, count, 1000),
        window_samples=1000,
        relative_cfo_hz=cfo,
    )
    np.testing.assert_allclose(MODULE.wrap_rad(np.angle(result.phasors) - phase), 0, atol=1e-6)
    np.testing.assert_allclose(result.coherence, 1, atol=1e-6)


def test_sample_level_mix_restores_650khz_before_32768_sample_average() -> None:
    rate = 10_000_000
    count = 100_000
    cfo = 650_000.0
    phase = -0.41
    time_s = np.arange(count) / rate
    iq = np.column_stack(
        (
            np.ones(count, dtype=np.complex64),
            np.exp(1j * (phase + 2 * np.pi * cfo * time_s)).astype(np.complex64),
        )
    )
    kwargs = {
        "valid": np.ones((count, 2), dtype=np.bool_),
        "device_counter_start": 123,
        "sample_rate_hz": rate,
        "starts": [0, 32_768, 65_536],
        "window_samples": 32_768,
    }
    raw = MODULE.direct_window_phasors(iq, relative_cfo_hz=0, **kwargs)
    corrected = MODULE.direct_window_phasors(iq, relative_cfo_hz=cfo, **kwargs)
    assert np.median(raw.coherence) < 0.01
    np.testing.assert_allclose(corrected.coherence, 1, atol=1e-6)
    np.testing.assert_allclose(MODULE.wrap_rad(np.angle(corrected.phasors) - phase), 0, atol=1e-5)


def test_fit_uses_integer_origin_and_predicts_without_eval_intercept() -> None:
    origin = 9_007_199_254_740_992
    rate = 10_000
    counters = origin + np.arange(10, dtype=np.int64) * 1000
    time_s = np.arange(10) / 10
    phase = 0.4 + 2 * np.pi * 3.0 * time_s + np.pi * 0.5 * time_s**2
    phasors = np.exp(1j * phase)
    cfo, drift, intercept = MODULE.fit_phase_frequency_rate(
        phasors, counters, integer_origin=origin, sample_rate_hz=rate, degree=2
    )
    error = MODULE.prediction_error(
        phasors,
        counters,
        integer_origin=origin,
        sample_rate_hz=rate,
        cfo_hz=cfo,
        rate_hz_s=drift,
        training_intercept_rad=intercept,
    )
    np.testing.assert_allclose(error, 0, atol=1e-10)


def test_holdout_is_disjoint_and_wrong_time_avoids_recurrence_offsets() -> None:
    starts = np.arange(0, 1_200_000, 20_000)
    train, held = MODULE.deterministic_holdout(starts, "visit:1")
    assert set(train).isdisjoint(held)
    assert sorted(np.concatenate([train, held]).tolist()) == starts.tolist()
    wrong = MODULE.wrong_time_starts(starts, visit_samples=1_200_000)
    assert np.all(abs(wrong - starts) == 130_000)


def test_forward_fit_is_invariant_to_future_samples() -> None:
    runner = _runner()
    count = 1_200_000
    time_s = np.arange(count) / runner.RATE
    iq = np.column_stack(
        (
            np.ones(count, dtype=np.complex64),
            np.exp(2j * np.pi * 650_000 * time_s).astype(np.complex64),
        )
    )
    changed = iq.copy()
    rng = np.random.default_rng(7)
    changed[600_000:, 1] = (
        rng.standard_normal(600_000) + 1j * rng.standard_normal(600_000)
    ).astype(np.complex64)
    valid = np.ones((count, 2), dtype=np.bool_)
    first = runner._fit_forward(iq, valid, 0, runner._starts(), 650_000.0)
    second = runner._fit_forward(changed, valid, 0, runner._starts(), 650_000.0)
    np.testing.assert_array_equal(first[0], second[0])
    np.testing.assert_array_equal(first[1], second[1])
    assert first[2] == second[2]
