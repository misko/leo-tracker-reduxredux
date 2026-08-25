from __future__ import annotations

import importlib.util
import sys
from dataclasses import replace
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest


def _tool() -> ModuleType:
    path = Path(__file__).parents[2] / "tools" / "report_d3_pilot_filter_prototypes.py"
    spec = importlib.util.spec_from_file_location("d3_pilot_filter_prototypes_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _window(
    tool: ModuleType,
    *,
    index: int = 0,
    start_s: float = 0.0,
    raw_disjoint: bool = True,
    frame_count: int = 75,
) -> object:
    time_s = start_s + np.arange(frame_count) / tool.FRAME_RATE_HZ
    cfo_hz = 20_000.0 - 3_000.0 * time_s
    return tool.WindowRows(
        index=index,
        center_time_s=start_s + 0.050,
        raw_disjoint=raw_disjoint,
        frame_index=np.arange(frame_count),
        absolute_time_s=time_s,
        cfo_hz=cfo_hz,
        sigma_hz=np.full(frame_count, 20.0),
        supported=np.ones(frame_count, dtype=bool),
        exact_coherence=np.full(frame_count, 0.50),
        control_coherence=np.full(frame_count, 0.05),
        frequency_innovation_hz=np.linspace(80.0, 120.0, frame_count),
        tracked_cfo_hz=cfo_hz - 100.0,
        tracked_rate_hz_s=np.full(frame_count, -3_000.0),
        tracked_rate_sigma_hz_s=np.full(frame_count, 100.0),
        phase_innovation_rad=np.zeros(frame_count),
        phase_update=np.ones(frame_count, dtype=bool),
        reacquired=np.zeros(frame_count, dtype=bool),
    )


def _synthetic_stub() -> dict[str, object]:
    row = {
        "repetitions": 1,
        "rmse_hz": {
            "trailing_20ms": 10.0,
            "robust_jump_filter": 8.0,
            "offline_quadratic": 5.0,
        },
        "mean_change_point_count": 0.0,
        "mean_locklet_count": 1.0,
    }
    return {"smooth_ramp": row, "jump_800hz": row}


def test_trailing_line_prediction_is_strictly_pre_update() -> None:
    tool = _tool()
    clean = _window(tool)
    contaminated_cfo = clean.cfo_hz.copy()
    contaminated_cfo[30:] += 5_000.0
    contaminated = replace(clean, cfo_hz=contaminated_cfo)

    clean_series = tool.trailing_line_predictions(clean, history_s=0.020)
    contaminated_series = tool.trailing_line_predictions(contaminated, history_s=0.020)
    key = clean.key(30)

    assert contaminated_series.prediction_by_key[key] == pytest.approx(
        clean_series.prediction_by_key[key], abs=1e-8
    )
    assert clean_series.prediction_by_key[key] == pytest.approx(clean.cfo_hz[30], abs=1e-8)
    assert contaminated_series.residual_by_key[key] == pytest.approx(5_000.0, abs=1e-8)


def test_source_npz_loader_preserves_the_replay_fields(tmp_path: Path) -> None:
    tool = _tool()
    window = _window(tool, index=3, start_s=1.0, frame_count=4)
    source = tmp_path / "source.npz"
    np.savez(
        source,
        window_index=np.full(4, window.index),
        window_center_time_s=np.full(4, window.center_time_s),
        window_raw_disjoint=np.full(4, window.raw_disjoint),
        frame_index=window.frame_index,
        absolute_time_s=window.absolute_time_s,
        absolute_cfo_measurement_hz=window.cfo_hz,
        measurement_sigma_hz=window.sigma_hz,
        measurement_supported=window.supported,
        exact_coherence=window.exact_coherence,
        control_coherence=window.control_coherence,
        frequency_innovation_hz=window.frequency_innovation_hz,
        tracked_absolute_cfo_hz=window.tracked_cfo_hz,
        tracked_rate_hz_s=window.tracked_rate_hz_s,
        tracked_rate_sigma_hz_s=window.tracked_rate_sigma_hz_s,
        phase_innovation_rad=window.phase_innovation_rad,
        phase_update=window.phase_update,
        reacquired=window.reacquired,
    )

    (loaded,) = tool._load_windows(source)
    assert (loaded.index, loaded.center_time_s, loaded.raw_disjoint) == (
        window.index,
        window.center_time_s,
        window.raw_disjoint,
    )
    for name in (
        "frame_index",
        "absolute_time_s",
        "cfo_hz",
        "sigma_hz",
        "supported",
        "exact_coherence",
        "control_coherence",
        "frequency_innovation_hz",
        "tracked_cfo_hz",
        "tracked_rate_hz_s",
        "tracked_rate_sigma_hz_s",
        "phase_innovation_rad",
        "phase_update",
        "reacquired",
    ):
        np.testing.assert_array_equal(getattr(loaded, name), getattr(window, name))


def test_frozen_holdout_never_refits_on_the_scored_tail() -> None:
    tool = _tool()
    clean = _window(tool)
    shifted_cfo = clean.cfo_hz.copy()
    shifted_cfo[clean.absolute_time_s >= 0.060] += 1_000.0
    shifted = replace(clean, cfo_hz=shifted_cfo)

    result = tool.frozen_block_holdout(shifted)
    scored_offsets = [
        offset
        for offset in range(len(shifted.frame_index))
        if shifted.key(offset) in result.residual_by_key
    ]

    assert scored_offsets
    assert min(shifted.absolute_time_s[scored_offsets]) >= 0.060
    assert max(shifted.absolute_time_s[: min(scored_offsets)]) < 0.060
    assert np.median(tuple(result.residual_by_key.values())) == pytest.approx(1_000.0, abs=1e-6)


def test_phase_arcs_split_on_time_gap_and_reacquisition() -> None:
    tool = _tool()
    window = _window(tool, frame_count=7)
    time_s = np.asarray((0.0, 0.001, 0.002, 0.006, 0.007, 0.008, 0.009))
    reacquired = np.zeros(7, dtype=bool)
    reacquired[4] = True
    window = replace(window, absolute_time_s=time_s, reacquired=reacquired)

    assert tool.phase_arcs(window) == ((0, 2), (3, 3), (5, 6))


def test_paired_bootstrap_is_paired_on_common_frames_and_whole_seconds() -> None:
    tool = _tool()
    common = ((0, 0), (0, 1), (1, 0), (1, 1))
    time_by_key = dict(zip(common, (0.2, 0.3, 1.2, 1.3), strict=True))
    baseline = tool.PredictionSeries(
        "baseline",
        {key: 4.0 for key in common},
        {},
        {},
    )
    candidate = tool.PredictionSeries(
        "candidate",
        {**{key: 2.0 for key in common}, (9, 9): 50_000.0},
        {},
        {},
    )

    result = tool.paired_block_bootstrap_improvement(
        candidate,
        baseline,
        time_by_key,
        draws=100,
    )

    assert result["common_frame_count"] == 4
    assert result["block_count"] == 2
    assert result["candidate_block_equal_rms_hz"] == pytest.approx(2.0)
    assert result["baseline_block_equal_rms_hz"] == pytest.approx(4.0)
    assert result["fractional_rms_improvement"] == pytest.approx(0.5)
    assert result["bootstrap_95_low"] == pytest.approx(0.5)
    assert result["bootstrap_95_high"] == pytest.approx(0.5)


def test_evaluation_scores_only_disjoint_windows_but_reports_all_phase_arcs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    tool = _tool()
    monkeypatch.setattr(tool, "synthetic_benchmark", _synthetic_stub)
    windows = (
        _window(tool, index=0, start_s=0.0, raw_disjoint=True),
        _window(tool, index=1, start_s=0.2, raw_disjoint=False),
    )
    summary = {
        "session_id": "cap-synthetic",
        "stream_id": "stream-1",
        "receiver_id": 1,
        "selection": "synthetic frozen selection",
        "window_count": 2,
        "raw_disjoint_window_count": 1,
        "frame_count": 150,
        "exact": {"qualified_count": 1},
        "rolled": {"qualified_count": 0, "supported_frames": 0},
        "exact_windows": [
            {"center_time_s": 0.05, "qualified": True},
            {"center_time_s": 0.25, "qualified": False},
        ],
    }

    evidence, plotting = tool.evaluate(windows, summary)

    assert evidence["corpus"]["raw_disjoint_windows_with_frames"] == 1
    assert evidence["corpus"]["raw_disjoint_supported_frame_count"] == 75
    assert evidence["models"]["offline_block_smoother"]["count"] == 75
    assert evidence["phase_lock"]["explicit_phase_arc_window_count"] == 2
    assert plotting["selected_windows"] == (windows[0],)

    destination = tmp_path / "representative.png"
    tool._style()
    tool._plot_representative_window(destination, plotting)
    assert destination.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")

    report = tmp_path / "report.md"
    tool._write_report(
        report,
        evidence,
        {
            "timeline": "timeline.png",
            "metrics": "metrics.png",
            "phase_synthetic": "phase.png",
            "representative": "representative.png",
        },
    )
    text = report.read_text(encoding="utf-8")
    assert "not an independent scientific validation" in text
    assert "Current V2 qualifies 1/2" in text
    assert "not a continuous 60 s replay" in text
    assert "These are modulo-pi locklets only" in text
    assert "Keep TLE matching downstream" in text
