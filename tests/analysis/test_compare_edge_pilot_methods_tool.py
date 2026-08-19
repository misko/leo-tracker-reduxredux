from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np


def _tool():
    path = Path(__file__).parents[2] / "tools" / "compare_edge_pilot_methods.py"
    spec = importlib.util.spec_from_file_location("compare_edge_pilot_methods_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_qin_injection_separates_exact_from_control_for_detector_family() -> None:
    tool = _tool()
    rate = 2_500_000
    epoch = 37
    cfo = 42_000.0
    samples = np.zeros(50_000, dtype=np.complex128)
    template = tool.qin_edge_pilot_frame(rate, "lower")
    frame = 0
    while True:
        start = epoch + round(frame * rate / tool.FRAME_RATE_HZ)
        if start + len(template) > len(samples):
            break
        indexes = np.arange(start, start + len(template))
        samples[start : start + len(template)] += template * np.exp(
            2j * np.pi * cfo * indexes / rate
        )
        frame += 1
    probe = tool.AcquiredProbe(0, 0, 0, 0, 0.0, epoch, cfo, 0.8, 0.9)

    metric = tool._metric_for_probe(probe, samples, rate)

    assert metric.anchor8_margin is not None and metric.anchor8_margin > 0.5
    assert metric.differential16_margin is not None and metric.differential16_margin > 0.5
    assert metric.differential32_margin is not None and metric.differential32_margin > 0.5
    assert metric.glrt32_margin is not None and metric.glrt32_margin > 0.5
    assert metric.glrt64_margin is not None and metric.glrt64_margin > 0.5
    assert metric.edge_tracker_margin is not None and metric.edge_tracker_margin > 0.2
    assert metric.differential32_residual_cfo_hz is not None
    assert abs(metric.differential32_residual_cfo_hz) < 1.0


def test_missing_acquisition_preserves_existing_symbolwise_and_qam_values() -> None:
    tool = _tool()
    probe = tool.AcquiredProbe(7, 0, 7, 875_000, 0.35, None, None, 0.04, 0.55)

    metric = tool._metric_for_probe(probe, np.zeros(50_000, np.complex128), 2_500_000)

    assert metric.index == 7
    assert metric.symbolwise_margin == 0.04
    assert metric.qam_accuracy == 0.55
    assert metric.anchor8_margin is None
    assert metric.glrt64_score is None


def test_track_components_do_not_bridge_unrelated_cfo_branches() -> None:
    tool = _tool()
    times = np.asarray([0.0, 0.05, 0.10, 0.15, 0.20])
    cfo = np.asarray([400_000.0, 398_000.0, 310_000.0, 308_000.0, 307_000.0])

    components = tool._track_components(times, cfo, np.ones(5, dtype=bool))

    assert [component.tolist() for component in components] == [[0, 1], [2, 3, 4]]
