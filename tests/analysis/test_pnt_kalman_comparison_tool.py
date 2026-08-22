from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _tool():
    path = Path(__file__).parents[2] / "tools" / "report_pnt_kalman_comparison.py"
    spec = importlib.util.spec_from_file_location("report_pnt_kalman_comparison", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_report_distinguishes_measurement_replay_from_closed_loop(tmp_path: Path) -> None:
    module = _tool()
    root = Path(__file__).parents[2]
    metrics = json.loads(
        (
            root
            / "reports/figures/2026_08_22_pnt_kalman_comparison"
            / "pnt-kalman-metrics.json"
        ).read_text(encoding="utf-8")
    )
    report = tmp_path / "report.md"

    module._report(report, metrics["segments"])
    rendered = report.read_text(encoding="utf-8")

    assert "offline Kalman measurement replay" in rendered
    assert "does not yet drive the next raw-IQ" in rendered
    assert "quadratic Doppler fit" in rendered
    assert "Frequency-only Kalman ablation" in rendered
    assert "Carrier-phase reset diagnostic" in rendered
    assert "frame-level phase-reference realignments" in rendered
    assert "carrier-phase-reset-tracking.png" in rendered
    assert "carrier-phase-reset-statistics.png" in rendered
    assert "carrier-phase-innovation-cdf.png" in rendered


def test_persisted_kalman_model_keeps_rates_constant() -> None:
    root = Path(__file__).parents[2]
    metrics = json.loads(
        (
            root
            / "reports/figures/2026_08_22_pnt_kalman_comparison"
            / "pnt-kalman-metrics.json"
        ).read_text(encoding="utf-8")
    )

    assert metrics["model"]["doppler_rate"] == "constant; zero process noise"
    assert metrics["model"]["code_rate"] == "constant; zero process noise"
    assert metrics["model"]["measurement_replay_not_raw_iq_closed_loop"] is True
    assert all("kalman_frequency_only_rate_hz_s" in item for item in metrics["segments"])
    assert all("phase_reset_rate_hz" in item for item in metrics["segments"])
    assert all(
        item["phase_accepted_count"]
        + item["phase_reset_count"]
        + item["phase_low_coherence_count"]
        == item["carrier_observation_count"]
        for item in metrics["segments"]
    )
