from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest


def _tool():
    path = Path(__file__).parents[2] / "tools" / "report_within_segment_frame_phase.py"
    spec = importlib.util.spec_from_file_location("report_within_segment_frame_phase", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _record(module, probe: int, frame: int, phase: float, control: float):
    return module.FrameRecord(
        segment="P1",
        probe_sample_start=probe,
        probe_time_s=20.25 + probe / 2_500_000,
        frame_index=frame,
        frame_midpoint_sample=probe + frame * 3_333,
        frame_midpoint_time_s=20.25 + (probe + frame * 3_333) / 2_500_000,
        phase_cycles=phase,
        coherence=0.9,
        median_absolute_residual_cycles=0.02,
        control_phase_cycles=control,
        control_coherence=0.1,
        control_median_absolute_residual_cycles=0.22,
    )


def test_lag_curve_uses_actual_frames_only_within_each_probe() -> None:
    module = _tool()
    rng = np.random.default_rng(4)
    records = tuple(
        _record(
            module,
            probe,
            frame,
            phase=(0.17 * frame + 0.31 * probe) % 1 - 0.5,
            control=float(rng.uniform(-0.5, 0.5)),
        )
        for probe in (0, 50_000)
        for frame in range(15)
    )

    groups = module._group_records(records)
    exact, counts = module._lag_curve(groups, max_lag=3)
    control, _ = module._lag_curve(groups, control=True, max_lag=3)

    assert counts.tolist() == [28, 26, 24]
    assert np.all(exact > 0.99)
    assert control[0] < 0.5


def test_candidate_selection_happens_after_independent_scoring() -> None:
    module = _tool()
    segment = module.SEGMENTS[0]
    expected = float(segment.frequency_hz(20.5))
    candidates = (
        module.Candidate(10, 20.5, 0, 4, expected + 20_000, 0.8, 0.1, 0.7),
        module.Candidate(10, 20.5, 1, 8, expected + 120, 0.4, 0.1, 0.3),
        module.Candidate(20, 20.6, 0, 4, float(segment.frequency_hz(20.6)) + 80, 0.2, 0.18, 0.02),
    )

    selected = module._select_candidates(segment, candidates)

    assert len(selected) == 1
    assert selected[0].rank == 1


def test_compact_state_artifact_is_reproducible(tmp_path: Path) -> None:
    module = _tool()
    record = _record(module, 0, 0, 0.1, -0.2)
    first = tmp_path / "first.jsonl.gz"
    second = tmp_path / "second.jsonl.gz"

    module._write_state_artifact({"P1": (record,)}, first)
    module._write_state_artifact({"P1": (record,)}, second)

    assert first.read_bytes() == second.read_bytes()


def test_synthetic_controls_separate_continuous_phase_from_resets() -> None:
    module = _tool()

    metrics = module._synthetic_metrics()

    assert metrics["continuous_lag1_concentration"] > 0.95
    assert metrics["random_reset_lag1_concentration"] < 0.35
    assert metrics["continuous_heldout_median_error_cycles"] < 0.05
    assert metrics["random_reset_heldout_median_error_cycles"] == pytest.approx(0.25, abs=0.03)


def test_report_distinguishes_actual_frames_from_probe_containers(tmp_path: Path) -> None:
    module = _tool()
    root = Path(__file__).parents[2]
    metrics = json.loads(
        (
            root
            / "reports/figures/2026_08_22_within_segment_frame_phase"
            / "within-segment-frame-phase-metrics.json"
        ).read_text(encoding="utf-8")
    )
    report = tmp_path / "report.md"

    module._report(metrics, report)
    rendered = report.read_text(encoding="utf-8")

    assert "actual approximately 1.33 ms Starlink frame" in rendered
    assert "20 ms probe is only" in rendered
    assert "does not claim one continuous" in rendered
    for label in ("P1", "P2", "P4", "P5"):
        assert f"## {label}" in rendered
