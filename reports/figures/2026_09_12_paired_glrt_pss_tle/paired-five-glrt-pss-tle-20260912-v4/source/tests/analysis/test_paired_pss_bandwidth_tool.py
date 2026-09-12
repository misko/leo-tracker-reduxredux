"""Offline experiment selection must preserve device gaps and joint evidence."""

import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def tool():
    path = Path(__file__).parents[2] / "tools" / "compare_paired_pss_bandwidth.py"
    spec = importlib.util.spec_from_file_location("paired_bandwidth_tool", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_segment_check_uses_device_gaps_and_accepts_exact_stop(tool):
    binding = {
        "sample_rate_hz": 100,
        "validity_inventory": {
            "segments": [
                {"segment_index": 0, "device_sample_start": 0, "device_sample_stop": 100},
                {"segment_index": 1, "device_sample_start": 200, "device_sample_stop": 300},
            ]
        },
    }
    assert tool.segment_for(binding, 0.5, 0.5) == 0
    assert tool.segment_for(binding, 0.5, 1.0) is None
    assert tool.segment_for(binding, 1.5, 1.0) is None
    assert tool.segment_for(binding, 2.0, 1.0) == 1
    assert tool.segment_for(binding, -0.1, 0.5) is None


def test_interval_requires_entire_glrt_window_and_counts_failures(tool):
    rows = [
        dict(global_start_time_s=a, global_end_time_s=b, glrt_margin=m, passed_margin_gate=p)
        for a, b, m, p in [
            (0, 0.02, 0.8, True),
            (0.01, 0.03, 0.1, False),
            (0.02, 0.04, None, False),
            (0.03, 0.05, 0.9, True),
        ]
    ]
    result = tool.interval_metrics(rows, 0.01, 0.03)
    assert result == dict(count=2, pass_fraction=0.0, median_margin=0.1)
    assert tool.interval_metrics([], 0, 1)["pass_fraction"] == 0


def test_product_digest_must_match_frozen_inventory(tool, tmp_path):
    (tmp_path / "product.json").write_text("{}")
    with pytest.raises(ValueError, match="digest mismatch"):
        tool.product(tmp_path, {"logical_uri": "bulk://product.json", "digest": "sha256:wrong"})


def test_timing_summary_unwraps_frame_boundary_and_retains_bad_peaks():
    path = Path(__file__).parents[2] / "tools" / "summarize_paired_pss_bandwidth.py"
    spec = importlib.util.spec_from_file_location("paired_bandwidth_summary", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rate = 25_000_000
    rows = []
    for i in range(1500):
        t = i / 750
        phase = 1 / 750 - 2e-6 + 4e-6 * t
        rows.append(
            dict(
                fractional_global_device_sample=t * rate,
                frame_phase_samples=(phase % (1 / 750)) * rate,
                peak_to_local_median=10,
            )
        )
    good = module.timing_diagnostics([{"windows": rows}], rate)
    assert good["apparent_stretch_ppm"] == pytest.approx(4, abs=1e-6)
    assert good["heldout_rms_ns"] < 0.001
    rows[501]["frame_phase_samples"] += 2e-6 * rate
    rows[501]["peak_to_local_median"] = 1
    bad = module.timing_diagnostics([{"windows": rows}], rate)
    assert bad["frame_count"] == 1500
    assert bad["heldout_rms_ns"] > 50
    assert bad["strong_fraction"] == pytest.approx(1499 / 1500)
