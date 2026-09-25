from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import numpy as np


def _tool() -> ModuleType:
    tools_root = Path(__file__).parents[2] / "tools"
    sys.path.insert(0, str(tools_root))
    try:
        path = tools_root / "report_five_dwell_multiscale_local_rates.py"
        spec = importlib.util.spec_from_file_location(
            "report_five_dwell_multiscale_local_rates_tool", path
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(tools_root))
    return module


def test_source_results_define_raw_acquisition_alias(tmp_path: Path) -> None:
    tool = _tool()
    rows = []
    for index in range(5):
        analysis_root = tmp_path / f"analysis-{index}"
        analysis_root.mkdir()
        (analysis_root / "standard.dealiased-trajectory-bank.v4.json").write_text(
            json.dumps(
                {
                    "branches": [
                        {
                            "branch_id": f"branch-{index}",
                            "start_s": 10.0,
                            "end_s": 11.0,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        rows.append(
            {
                "session_id": f"cap-{index}-abcdef{index}",
                "analysis_run_id": f"run-{index}",
                "stream_id": "stream-0",
                "receiver_id": 1,
                "edge": "lower",
                "analysis_root": str(analysis_root),
                "branch_id": f"branch-{index}",
                "start_s": 10.0,
                "end_s": 11.0,
                "trajectory_reference_time_s": 10.0,
                "trajectory_coefficients_hz": [-4_000.0, -186_000.0 + index],
                "anchor": {"time_s": 10.5},
            }
        )
    source = tmp_path / "source.json"
    source.write_text(json.dumps({"results": rows}), encoding="utf-8")

    specs = tool.load_specs(source)

    assert len(specs) == 5
    assert specs[0].coefficients_hz == (-4_000.0, -186_000.0)


def test_candidate_selection_keeps_source_alias_timing_epoch(tmp_path: Path) -> None:
    tool = _tool()
    spec = tool.DwellSpec(
        label="D1",
        session_id="capture",
        run_id="run",
        stream_id="stream-0",
        receiver_id=1,
        edge=tool.StarlinkEdge.LOWER,
        analysis_root=tmp_path,
        branch_id="branch",
        start_s=10.0,
        end_s=11.0,
        reference_time_s=10.0,
        coefficients_hz=(-4_000.0, -186_000.0),
        anchor_time_s=10.5,
    )

    def candidate(rank: int, epoch: int, cfo_hz: float) -> dict[str, object]:
        return {
            "rank": rank,
            "local_epoch_sample": epoch,
            "scores": [
                {
                    "method": "glrt64",
                    "tracking_cfo_hz": cfo_hz,
                    "exact_score": 0.6,
                    "control_score": 0.04,
                    "margin": 0.56,
                }
            ],
        }

    scan = {
        "detections": [
            {
                "time_s": 10.5,
                "sample_start": 25_000_000,
                "candidates": [
                    candidate(0, 2_200, -188_050.0),
                    candidate(1, 700, 39_200.0),
                ],
            }
        ]
    }

    selected = tool.select_candidate_windows(spec, scan)

    assert len(selected) == 1
    assert selected[0].local_epoch_sample == 2_200
    assert selected[0].initial_cfo_hz == -188_050.0


def test_normalized_frequency_curve_recovers_injected_residual() -> None:
    tool = _tool()
    frame_count = 3
    symbol_count = len(tool.SYMBOLS)
    times = np.tile(np.arange(symbol_count) * 4.4e-6, (frame_count, 1))
    injected_hz = 1_250.0
    values = np.exp(2j * np.pi * injected_hz * times)
    indexes = np.arange(0, symbol_count, 2)

    power, _ceiling = tool.normalized_frequency_curves(values, times, indexes)
    peaks = tool.RESIDUAL_GRID_HZ[np.argmax(power, axis=1)]

    assert np.allclose(peaks, injected_hz)


def _summary_document() -> dict[str, object]:
    dwells = []
    for index in range(5):
        glrt = -5_000.0 - 100.0 * index
        local = -3_500.0 - 100.0 * index
        dwells.append(
            {
                "spec": {
                    "label": f"D{index + 1} · dwell{index + 1}",
                    "branch_coefficients_hz": [glrt, -100_000.0],
                },
                "rate_analysis": {
                    "status": "complete",
                    "common_slope": {
                        "shared_slope_hz_s": local,
                        "leave_one_segment_out_rms_hz_s": 200.0,
                    },
                    "errors": {
                        "source_glrt_slope": {"odd_validation": {"rms_hz": 60.0}},
                        "common_slope": {"odd_validation": {"rms_hz": 30.0}},
                    },
                },
                "gate_sensitivity": [
                    {
                        "exact_gate": gate,
                        "common_slope_hz_s": local,
                        "coherent_segment_count": 12,
                    }
                    for gate in (0.05, 0.10, 0.20, 0.30)
                ],
            }
        )
    return {"dwells": dwells}


def test_cross_dwell_figures_render(tmp_path: Path) -> None:
    tool = _tool()
    document = _summary_document()
    rate_path = tmp_path / "rates.png"
    gate_path = tmp_path / "gates.png"

    tool.render_rate_summary(rate_path, document)
    tool.render_gate_sensitivity(gate_path, document)

    assert rate_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert gate_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
