"""A transmitter channel correction agrees across RX and differs across CH."""

import importlib
import sys
from pathlib import Path

import numpy as np
from test_dsx01_rf_clock_tool import problem_inputs


def test_channel_clocks_recover_opposite_rates_and_agree_between_receivers():
    path = str(Path(__file__).resolve().parents[2] / "tools")
    sys.path.insert(0, path)
    try:
        tool = importlib.import_module("prototype_dsx01_channel_clock")
    finally:
        sys.path.remove(path)
    scan, seed = problem_inputs()
    base = tool.AnchoredFamilies(scan, seed, "shared_phase", False, (0, 0))
    f, _ = base.predicted(base.initial)
    for t, block in zip(scan.tracks, base.slices, strict=True):
        rate = 2 if t["channel"] == 1 else -2
        t["values"] = t["rf_hz"] / 11.5e9 * (f[block] + rate * (t["times"] - 150))
    p = tool.ChannelClockFamilies(
        scan, seed, "shared_phase", False, (0, 0), grouping="channel", rate_sigma=5
    )
    corrected, _ = p.predicted(p.initial)
    change = corrected - f
    for k in (0, 1):
        np.testing.assert_allclose(change[base.slices[k]], change[base.slices[k + 2]], atol=1e-8)
    for t, block in zip(scan.tracks, base.slices, strict=True):
        rate = np.polyfit(t["times"] - 150, change[block], 1)[0]
        assert abs(rate - (2 if t["channel"] == 1 else -2)) < 0.01
    assert len(p.initial) == len(base.initial)
