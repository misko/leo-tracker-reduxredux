"""Actual native progressive DSP, causal filtering, and soft-budget accounting."""

import ctypes as ct

import numpy as np
import pytest

from leo.analysis.starlink.templates import qin_edge_pilot_frame
from tools.investigate_adaptive_decision_budget import control_iq, decimate_window, taps_for
from tools.native_presence import Result, pointer
from tools.prepare_progressive_decision_replay import build


class ProgressiveResult(ct.Structure):
    _fields_ = [
        (n, ct.c_uint32) for n in ("probes", "mask", "positive_mask", "outcome", "budget_exceeded")
    ]
    _fields_ += [
        (n, ct.c_double)
        for n in ("filter_cpu_ms", "confirm_cpu_ms", "total_cpu_ms", "total_wall_ms")
    ]
    _fields_ += [("probe_cpu_ms", ct.c_double * 6), ("confirmations", Result * 6)]


@pytest.fixture(scope="module")
def native(tmp_path_factory):
    lib = ct.CDLL(
        str(build(tmp_path_factory.mktemp("progressive") / "progressive.so", shared=True))
    )
    lib.leo_progressive_filter.argtypes = [
        ct.c_void_p,
        ct.c_size_t,
        ct.c_uint,
        ct.c_void_p,
        ct.c_void_p,
    ]
    lib.leo_progressive_filter.restype = ct.c_int
    lib.leo_progressive_create.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_size_t, ct.c_void_p]
    lib.leo_progressive_create.restype = ct.c_void_p
    lib.leo_progressive_destroy.argtypes = [ct.c_void_p]
    lib.leo_progressive_run.argtypes = [
        ct.c_void_p,
        ct.c_void_p,
        ct.c_size_t,
        ct.c_double,
        ct.POINTER(ProgressiveResult),
    ]
    lib.leo_progressive_run.restype = ct.c_int
    return lib


def run(native, iq, budget):
    templates = [
        qin_edge_pilot_frame(5_000_000, "lower", symbol_roll=k).astype("complex128")
        for k in (0, 17)
    ]
    taps = taps_for(5_000_000).astype("float32")
    w = native.leo_progressive_create(
        pointer(templates[0]), pointer(templates[1]), len(templates[0]), pointer(taps)
    )
    assert w
    try:
        result = ProgressiveResult()
        assert native.leo_progressive_run(w, pointer(iq), len(iq), budget, ct.byref(result)) == 0
        return result
    finally:
        native.leo_progressive_destroy(w)


def test_fp32_filter_keeps_causal_history_and_quantization_within_one_lsb(native):
    iq = np.random.default_rng(15).integers(-32768, 32767, (1_200_000, 2), dtype="int16")
    taps = taps_for(5_000_000).astype("float32")
    for window in (0, 1, 5):
        got = np.empty((100000, 2), dtype="int16")
        assert (
            native.leo_progressive_filter(pointer(iq), len(iq), window, pointer(taps), pointer(got))
            == 0
        )
        expected, _ = decimate_window(iq, 5_000_000, window)
        assert np.max(np.abs(got.astype(int) - expected)) <= 1


def test_complete_negative_and_partial_budget_exhaustion_are_distinct(native):
    iq = np.zeros((1_200_000, 2), dtype="int16")
    complete = run(native, iq, 0)
    assert (complete.probes, complete.mask, complete.outcome) == (6, 63, 2)
    partial = run(native, iq, 0.01)
    assert partial.outcome == 0 and partial.budget_exceeded == 1
    assert partial.probes <= 1 and partial.mask != 63


@pytest.mark.parametrize("window,probes", [(0, 1), (5, 6)])
def test_progressive_confirmation_stops_only_after_a_positive(native, window, probes):
    iq = control_iq("lower", "pilot", window, 100 + window)
    result = run(native, iq, 0)
    assert result.outcome == 1 and result.positive_mask == 1 << window
    assert result.probes == probes
    assert not result.budget_exceeded


def test_positive_completing_after_budget_is_unknown(native):
    result = run(native, control_iq("lower", "pilot", 0, 100), 0.01)
    assert result.budget_exceeded == 1 and result.outcome == 0


def test_bad_window_rejected_without_output_changes(native):
    iq = np.zeros((1_200_000, 2), dtype="int16")
    taps = taps_for(5_000_000).astype("float32")
    output = np.full((100000, 2), 123, dtype="int16")
    assert (
        native.leo_progressive_filter(pointer(iq), len(iq), 6, pointer(taps), pointer(output)) == -1
    )
    assert np.all(output == 123)
