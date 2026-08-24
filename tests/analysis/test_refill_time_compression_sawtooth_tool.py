from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest
from PIL import Image

ROOT = Path(__file__).parents[2]


def _tool() -> ModuleType:
    path = ROOT / "tools" / "report_refill_time_compression_sawtooth.py"
    spec = importlib.util.spec_from_file_location(
        "report_refill_time_compression_sawtooth_tool", path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_core_formulas_are_signed_and_intercept_aware() -> None:
    tool = _tool()

    assert tool.circular_difference(1_900.0, 3_000.0) == -1_100.0
    assert tool.circular_difference(-1_900.0, 3_000.0) == 1_100.0
    fit = tool._ols_with_intercept([0.0, 0.1, 0.2], [50.0, -350.0, -750.0])
    assert fit["slope"] == pytest.approx(-4_000.0)
    assert fit["intercept"] == pytest.approx(50.0)
    assert fit["r_squared"] == pytest.approx(1.0)
    assert fit["rms"] == pytest.approx(0.0, abs=1e-12)


@pytest.mark.real_corpus
def test_boundary_mechanism_reproduces_37_event_regression() -> None:
    tool = _tool()

    result = tool._analyze_boundary_mechanism(
        ROOT / tool.DEFAULT_BOUNDARY_JSON,
        recording_root=tool.DEFAULT_RECORDING_ROOT,
    )

    assert result is not None
    assert result["event_count"] == 37
    assert result["host_excess_direct_jump_correlation"] == pytest.approx(-0.9873050782, abs=1e-10)
    assert result["host_excess_direct_jump_ols_slope_hz_s"] == pytest.approx(
        -3_758.0402182, abs=1e-6
    )
    assert result["host_excess_direct_jump_ols_intercept_hz"] == pytest.approx(49.6849018, abs=1e-6)
    assert result["host_excess_direct_jump_ols_r_squared"] == pytest.approx(0.9747713175, abs=1e-10)
    assert result["host_excess_direct_jump_ols_rms_hz"] == pytest.approx(25.7488683, abs=1e-6)
    assert result["timing_magnitude_prediction_correlation"] == pytest.approx(
        0.9764523782, abs=1e-10
    )
    assert result["timing_magnitude_prediction_median_absolute_error_samples"] == pytest.approx(
        73.4716667, abs=1e-6
    )


def test_frozen_evidence_renders_without_corpus_access(tmp_path: Path) -> None:
    tool = _tool()
    evidence_path = ROOT / tool.DEFAULT_EVIDENCE
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))

    assert evidence["boundary_mechanism_470384"]["event_count"] == 37
    assert evidence["standard_v1_refill_geometry"]["aggregate"]["crossing_count"] == 44_101
    assert evidence["standard_v1_refill_geometry"]["source_sha256"] == (
        "sha256:711fcc34a170acd3a59baa0f1444ad4535f26099f881eeceb2c62c67a68b47af"
    )
    assert evidence["external_scanner_control"]["analysis_recomputed_by_this_tool"] is False
    assert evidence["host_retiming_diagnostic_only"] is True

    output_dir = tmp_path / "figures"
    report = tmp_path / "report.md"
    tool.render(evidence, output_dir=output_dir, report=report)

    for name in (
        "refill-event-alignment-and-timing.png",
        "ten-dwell-rate-closure.png",
        "refill-closeup-geometry.png",
    ):
        with Image.open(output_dir / name) as image:
            assert image.width > 1_500
            assert image.height > 700
    text = report.read_text(encoding="utf-8")
    assert r"\Delta f_{\mathrm{jump}} \approx \dot f_{\mathrm{local}}\,\delta" in text
    assert "host-retimed numbers below are therefore **diagnostic only**" in text
    assert "additive V2 product, preserving immutable V1" in text
