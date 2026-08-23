from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
from PIL import Image


def _tool():
    path = Path(__file__).parents[2] / "tools" / "report_piecewise_pilot_doppler_rate_figures.py"
    spec = importlib.util.spec_from_file_location("piecewise_pilot_doppler_rate_report_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _candidate(cfo_hz: float, margin: float, *, rank: int) -> dict:
    return {
        "rank": rank,
        "scores": [
            {
                "method": "glrt64",
                "tracking_cfo_hz": cfo_hz,
                "margin": margin,
                "exact_score": margin + 0.04,
                "control_score": 0.04,
            }
        ],
    }


def test_raw_inventory_and_dense_selection_are_explicit() -> None:
    tool = _tool()
    scan = {
        "detections": [
            {
                "time_s": 1.0,
                "candidates": [
                    _candidate(1_002.0, 0.20, rank=0),
                    _candidate(1_050.0, 0.30, rank=1),
                ],
            },
            {
                "time_s": 2.0,
                "candidates": [_candidate(1_001.0, 0.01, rank=0)],
            },
            {
                "time_s": 3.0,
                "candidates": [_candidate(5_000.0, 0.20, rank=0)],
            },
            {
                "time_s": 4.0,
                "candidates": [
                    _candidate(980.0, 0.20, rank=0),
                    _candidate(1_010.0, 0.15, rank=1),
                ],
            },
        ]
    }
    target = tool.TargetTrack(
        trajectory_id="trajectory",
        coefficients_hz=(1_000.0,),
        reference_time_s=0.0,
        start_s=0.0,
        end_s=5.0,
        polynomial_degree=0,
        branch_id="branch",
    )

    points = tool._raw_glrt_points(scan)
    selected = tool._selected_dense_windows(
        scan,
        target,
        start_s=1.0,
        end_s=4.0,
        minimum_margin=0.05,
        maximum_model_error_hz=100.0,
    )

    assert len(points) == 6
    assert [(item.time_s, item.cfo_hz, item.rank) for item in selected] == [
        (1.0, 1_002.0, 0),
        (4.0, 1_010.0, 1),
    ]


def test_polynomial_tracks_use_the_persisted_reference_epoch() -> None:
    tool = _tool()
    track = tool.PolynomialTrack(
        trajectory_id="trajectory",
        coefficients_hz=(2.0, -3.0, 10.0),
        reference_time_s=5.0,
        start_s=4.0,
        end_s=6.0,
        polynomial_degree=2,
    )

    np.testing.assert_allclose(track.frequency_hz(np.asarray((4.0, 5.0, 6.0))), (15, 10, 9))


def test_raw_window_and_full_context_figures_render(tmp_path: Path) -> None:
    tool = _tool()
    times = np.linspace(0.0, 5.0, 41)
    target = tool.TargetTrack(
        trajectory_id="target",
        coefficients_hz=(-100.0, 2_000.0),
        reference_time_s=0.0,
        start_s=0.0,
        end_s=5.0,
        polynomial_degree=1,
        branch_id="branch",
    )
    points = tuple(
        tool.GlrtPoint(
            time_s=float(time_s),
            cfo_hz=float(target.frequency_hz(time_s) + offset_hz),
            margin=0.20 if abs(offset_hz) < 100 else 0.01,
            exact_score=0.24 if abs(offset_hz) < 100 else 0.05,
            control_score=0.04,
            rank=rank,
        )
        for time_s in times
        for rank, offset_hz in enumerate((-20_000.0, 25.0, 18_000.0))
    )
    selected = tuple(item for item in points if item.rank == 1 and 1.0 <= item.time_s <= 3.0)
    raw_tracks = (
        tool.PolynomialTrack("d1", (-100.0, 2_000.0), 0.0, 0.0, 5.0, 1),
        tool.PolynomialTrack("d2", (2.0, -105.0, 2_000.0), 0.0, 0.0, 5.0, 2),
        tool.PolynomialTrack("d3", (0.2, 1.0, -103.0, 2_000.0), 0.0, 0.0, 5.0, 3),
    )
    detail_path = tmp_path / "detail.png"
    full_path = tmp_path / "full.png"

    tool._plot_glrt_window_context(
        points,
        selected,
        target,
        start_s=1.0,
        end_s=3.0,
        minimum_margin=0.05,
        maximum_model_error_hz=2_500.0,
        path=detail_path,
    )
    tool._plot_full_glrt_track_context(
        points,
        raw_tracks,
        selected,
        target,
        start_s=1.0,
        end_s=3.0,
        path=full_path,
    )

    for path in (detail_path, full_path):
        with Image.open(path) as image:
            assert image.width > 1_000
            assert image.height > 600
