from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _tool() -> ModuleType:
    tools_root = Path(__file__).parents[2] / "tools"
    sys.path.insert(0, str(tools_root))
    path = tools_root / "report_470384_qin_frames_25_45.py"
    spec = importlib.util.spec_from_file_location("report_470384_qin_frames_25_45_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _candidate(cfo_hz: float, margin: float, *, rank: int, epoch: int) -> dict:
    return {
        "rank": rank,
        "local_epoch_sample": epoch,
        "scores": [
            {
                "method": "glrt64",
                "tracking_cfo_hz": cfo_hz,
                "exact_score": 0.1 + margin,
                "control_score": 0.1,
                "margin": margin,
            }
        ],
    }


def test_selected_branches_clips_sorts_and_uses_selected_model() -> None:
    tool = _tool()
    bank = {
        "branches": [
            {
                "branch_id": "sha256:later",
                "selected_model_id": "model-later",
                "start_s": 40.0,
                "end_s": 50.0,
                "models": [
                    {
                        "model_id": "model-later",
                        "reference_time_s": 40.0,
                        "coefficients_hz": [-4_000.0, 300_000.0],
                    }
                ],
            },
            {
                "branch_id": "sha256:earlier",
                "selected_model_id": "model-earlier",
                "start_s": 20.0,
                "end_s": 30.0,
                "models": [
                    {
                        "model_id": "not-selected",
                        "reference_time_s": 20.0,
                        "coefficients_hz": [1.0],
                    },
                    {
                        "model_id": "model-earlier",
                        "reference_time_s": 20.0,
                        "coefficients_hz": [-3_000.0, 200_000.0],
                    },
                ],
            },
        ]
    }

    branches = tool.selected_branches(bank, start_s=25.0, end_s=45.0)

    assert [branch.branch_id for branch in branches] == ["sha256:earlier", "sha256:later"]
    assert [(branch.start_s, branch.end_s) for branch in branches] == [
        (25.0, 30.0),
        (40.0, 45.0),
    ]
    assert branches[0].frequency_hz(25.0) == pytest.approx(185_000.0)


def test_nearest_candidate_selection_does_not_gate_on_qin_margin() -> None:
    tool = _tool()
    branch = tool.Branch(
        index=0,
        label="B1",
        branch_id="branch",
        model_id="model",
        start_s=25.0,
        end_s=25.1,
        reference_time_s=25.0,
        coefficients_hz=(100_000.0,),
    )
    scan = {
        "detections": [
            {
                "time_s": 25.0,
                "sample_start": 1_000,
                "candidates": [
                    _candidate(100_020.0, -0.08, rank=3, epoch=17),
                    _candidate(101_000.0, 0.90, rank=0, epoch=3),
                ],
            }
        ]
    }

    windows = tool.nearest_candidate_windows(scan, (branch,))

    assert len(windows) == 1
    assert windows[0].candidate_rank == 3
    assert windows[0].glrt_margin == pytest.approx(-0.08)
    assert windows[0].selection_model_error_hz == pytest.approx(20.0)
    assert windows[0].aligned_sample_start == 1_017


def test_shared_candidate_window_count_is_explicit() -> None:
    tool = _tool()
    branches = tuple(
        tool.Branch(
            index=index,
            label=f"B{index + 1}",
            branch_id=f"branch-{index}",
            model_id=f"model-{index}",
            start_s=25.0,
            end_s=26.0,
            reference_time_s=25.0,
            coefficients_hz=(100_000.0,),
        )
        for index in range(2)
    )
    common = {
        "detection_time_s": 25.0,
        "probe_sample_start": 1_000,
        "aligned_sample_start": 1_010,
        "candidate_rank": 0,
        "local_epoch_sample": 10,
        "initial_cfo_hz": 100_000.0,
        "glrt_exact_score": 0.2,
        "glrt_control_score": 0.1,
        "glrt_margin": 0.1,
        "selection_model_error_hz": 0.0,
    }
    windows = tuple(
        tool.CandidateWindow(association_index=index, branch_index=index, **common)
        for index in range(2)
    )

    overlap = tool.shared_candidate_windows(branches, windows)

    assert len(overlap) == 1
    assert overlap[0]["shared_candidate_window_count"] == 1


def test_all_requested_figures_render(tmp_path: Path) -> None:
    tool = _tool()
    branch = tool.Branch(
        index=0,
        label="B1",
        branch_id="branch",
        model_id="model",
        start_s=25.0,
        end_s=25.1,
        reference_time_s=25.0,
        coefficients_hz=(-3_800.0, 300_000.0),
    )
    windows = tuple(
        tool.CandidateWindow(
            association_index=index,
            branch_index=0,
            detection_time_s=25.0 + index * 0.025,
            probe_sample_start=1_000 + index * 100,
            aligned_sample_start=1_010 + index * 100,
            candidate_rank=0,
            local_epoch_sample=10,
            initial_cfo_hz=300_000.0,
            glrt_exact_score=0.2,
            glrt_control_score=0.1,
            glrt_margin=0.1,
            selection_model_error_hz=10.0,
        )
        for index in range(4)
    )
    rows = []
    for window in windows:
        for frame in range(15):
            time_s = window.detection_time_s + frame / 750
            model_hz = branch.frequency_hz(time_s)
            rows.append(
                tool.FrameRow(
                    row_index=len(rows),
                    association_index=window.association_index,
                    branch_index=0,
                    frame_index=frame,
                    reference_time_s=time_s,
                    absolute_cfo_hz=model_hz + frame * 2,
                    model_cfo_hz=model_hz,
                    residual_cfo_hz=frame * 2,
                    residual_from_initial_hz=frame * 2,
                    frequency_uncertainty_hz=10.0,
                    exact_coherence=0.12,
                    control_coherence=0.04,
                    coherence_margin=0.08,
                    phase_residual_rms_rad=0.2,
                    model_proximate_window=True,
                    direct_qin_match=True,
                    fit_eligible=True,
                )
            )
    values = tuple(rows)
    destinations = [tmp_path / name for name in ("overview.png", "raster.png", "fits.png")]

    tool.render_overview(
        destinations[0],
        branches=(branch,),
        windows=windows,
        rows=values,
        start_s=25.0,
        end_s=25.1,
    )
    tool.render_raster(
        destinations[1],
        branches=(branch,),
        windows=windows,
        rows=values,
        start_s=25.0,
        end_s=25.1,
    )
    tool.render_fits(
        destinations[2],
        branches=(branch,),
        rows=values,
        coherent_by_branch={0: ()},
        start_s=25.0,
        end_s=25.1,
    )

    assert all(path.is_file() and path.stat().st_size > 0 for path in destinations)
