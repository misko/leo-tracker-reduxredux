from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _tool():
    path = Path(__file__).parents[2] / "tools" / "report_pnt_phase_doppler_comparison.py"
    spec = importlib.util.spec_from_file_location("report_pnt_phase_doppler_comparison", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_report_states_constant_rate_and_paper_scope(tmp_path: Path) -> None:
    module = _tool()
    root = Path(__file__).parents[2]
    metrics = json.loads(
        (
            root
            / "reports/figures/2026_08_22_pnt_phase_doppler_comparison"
            / "pnt-phase-doppler-metrics.json"
        ).read_text(encoding="utf-8")
    )
    report = tmp_path / "report.md"

    module._report(report, metrics["segments"])
    rendered = report.read_text(encoding="utf-8")

    assert "only one linear Doppler trajectory" in rendered
    assert "PNT-style edge-pilot tracker" in rendered
    assert "does not implement Kassas's blind full-beacon estimator" in rendered
    assert "quadratic phase expression is only the exact integral" in rendered
    assert "Production Standard" in rendered
    assert "Production Research" in rendered
    for label in ("P1", "P2", "P4", "P5"):
        assert f"| {label} |" in rendered


def test_persisted_method_is_degree_one_only() -> None:
    root = Path(__file__).parents[2]
    metrics = json.loads(
        (
            root
            / "reports/figures/2026_08_22_pnt_phase_doppler_comparison"
            / "pnt-phase-doppler-metrics.json"
        ).read_text(encoding="utf-8")
    )

    assert metrics["method"]["frequency_model"] == "degree one only (constant Doppler rate)"
    assert all("pnt_frame_rate_hz_s" in item for item in metrics["segments"])
