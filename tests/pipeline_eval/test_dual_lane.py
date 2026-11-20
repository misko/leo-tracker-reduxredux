import ctypes as ct
from threading import Lock

import numpy as np
import pytest

from tools.pipeline_eval.qualification.dual_lane_build import NEW_SYMBOL, single
from tools.pipeline_eval.qualification.dual_lane_results import stats
from tools.pipeline_eval.variants.dual_lane import DualLane


def test_internal_one_receiver_port_preserves_existing_short_window_entry():
    snippet = """static int analyze_profiled(...)
    context->receiver_count != 2 || context->refinement_mode != 3 ||
int leo_single_rx_glrt_analyze_short_window(leo_single_rx_glrt *context,
"""
    patched = single(snippet)
    assert "context->refinement_mode != 3 ||" in patched
    assert patched.count(f"int {NEW_SYMBOL}(") == 1
    assert patched.count("int leo_single_rx_glrt_analyze_short_window(") == 1
    assert "const int32_t hints[2]={hint,-1};" in patched


def test_complete_dual_input_requires_both_physical_receiver_lanes():
    detector = DualLane.__new__(DualLane)
    detector.lock = Lock()
    detector.ctx = ct.c_void_p(1)
    with pytest.raises(ValueError, match="two complete contiguous CI16"):
        detector.analyze(np.zeros((200000, 1, 2), dtype="<i2"))
    with pytest.raises(ValueError, match="two complete contiguous CI16"):
        detector.analyze(np.zeros((200000, 2, 2), dtype="<f4"))


def test_typed_deadline_and_completed_decoding_count_hits_separately():
    base = dict(mode="fifth", role="split-parallel", lanes=[{"cpu_ns": 10}, {"cpu_ns": 11}])
    rows = [
        dict(base, wall_ns=wall, typed_ns=typed, cpu_ns=31_000_000)
        for wall, typed in ((19_998_000, 19_995_000), (20_003_000, 19_999_000))
    ]
    result = stats(rows, "fifth", "split-parallel")
    assert (result["calls"], result["typed_within_20ms"], result["decoded_within_20ms"]) == (
        2,
        2,
        1,
    )
    assert result["lane1_cpu_p50_ms"] == pytest.approx(0.000011)
