"""Exercise the actual native/causal boundary before frozen IQ evaluation."""

from pathlib import Path
import sys

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from decision import CacheKey, TG11Detector
from native_engine import NativeTG11


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
def test_actual_native_zero_dwell_returns_fresh_negative_both_receivers(rate):
    raw = np.zeros((rate * 120 // 1000, 2, 2), dtype=np.int16)
    raw.flags.writeable = False
    with NativeTG11(rate, "lower", library=HERE / "libtg11.so") as engine:
        detector = TG11Detector(engine)
        for receiver in (0, 1):
            key = CacheKey("constructed-zero", receiver, 1, "lower", rate, "tune", "cal")
            result = detector.process(raw, key, start_counter=2**55, visit_index=0)
            assert not result.active
            assert result.pair is None
            assert result.route == "blind_cold"
            assert result.screen_windows == 11
        assert not detector.states
        assert len(detector.last_inputs) == 2
    assert not np.any(raw)
