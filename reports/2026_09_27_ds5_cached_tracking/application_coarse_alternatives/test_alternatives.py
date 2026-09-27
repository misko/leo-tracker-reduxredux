from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(HERE), str(ROOT / "src")]

from alternatives import grid_delta, numpy_correlate_grid, numpy_fft_grid  # noqa: E402
from leo.analysis.starlink import acquisition  # noqa: E402
from leo.analysis.starlink.templates import FRAME_RATE_HZ, qin_edge_pilot_frame  # noqa: E402


def small_fixture(rate: int, kind: str) -> np.ndarray:
    count = 12_000
    if kind == "zero":
        return np.zeros(count, np.complex128)
    if kind == "random":
        rng = np.random.default_rng(rate + 91)
        return np.asarray(rng.normal(size=count) + 1j * rng.normal(size=count), np.complex128)
    values = np.zeros(count, np.complex128)
    template = np.asarray(qin_edge_pilot_frame(rate, "lower"), np.complex128)
    frame = 0
    while True:
        start = 31 + round(frame * rate / FRAME_RATE_HZ)
        if start + len(template) > count:
            break
        values[start:start + len(template)] += template
        frame += 1
    return values


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
@pytest.mark.parametrize("kind", ["random", "zero", "pilot"])
def test_alternatives_preserve_small_rounded_template_grids(rate, kind):
    values = small_fixture(rate, kind)
    before = hashlib.sha256(values).hexdigest()
    template = np.asarray(qin_edge_pilot_frame(rate, "lower"), np.complex128)
    frequencies = (-160_000.0, 0.0, 160_000.0)
    args = (
        values, template, float(rate), frequencies,
        acquisition.DEFAULT_ANCHOR_SYMBOLS, min(1024, round(rate / FRAME_RATE_HZ)),
    )
    expected = acquisition._folded_anchor_score_grid_native(*args)
    for function in (numpy_correlate_grid, numpy_fft_grid):
        delta = grid_delta(expected, function(*args))
        assert delta["shape_match"] and delta["finite"] and delta["peak_indexes_exact"]
        assert delta["maximum_absolute_error"] <= 1e-10
    assert hashlib.sha256(values).hexdigest() == before


def test_source_lock() -> None:
    spec = importlib.util.spec_from_file_location("coarse_alternative_runner", HERE / "run_experiment.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    lock = module.verify_source_lock()
    assert lock["stage"] == "frozen_before_timing_outcomes"


def test_result_stops_at_failed_component_gate() -> None:
    result = __import__("json").loads((HERE / "results.json").read_text())
    assert result["fresh_holdout_opened"] is False
    assert result["status"] == "rejected_at_component_gate"
    assert result["promoted_variants"] == []
    assert result["saved_iq_application_calls_run"] is False
    assert result["science_pass"] == {"numpy_correlate": True, "numpy_fft": True}
    assert result["promotion_gate_speedup"] == 10.0
    for rate in ("2500000", "5000000"):
        for variant in ("numpy_correlate", "numpy_fft"):
            assert result["timing"][rate]["speedup_vs_production"][variant]["process_cpu"] < 1


def test_result_science_errors_and_peaks_obey_frozen_gate() -> None:
    result = __import__("json").loads((HERE / "results.json").read_text())
    for kinds in result["science"].values():
        for variants in kinds.values():
            for delta in variants.values():
                assert delta["shape_match"] and delta["finite"]
                assert delta["peak_indexes_exact"]
                assert delta["maximum_absolute_error"] <= 1e-10
