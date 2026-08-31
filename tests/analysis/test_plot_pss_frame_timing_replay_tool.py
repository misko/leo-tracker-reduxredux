from __future__ import annotations

import importlib.util
import struct
import sys
from pathlib import Path

TOOL_PATH = Path(__file__).parents[2] / "tools" / "plot_pss_frame_timing_replay.py"
SPEC = importlib.util.spec_from_file_location("plot_pss_frame_timing_replay", TOOL_PATH)
assert SPEC is not None and SPEC.loader is not None
tool = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = tool
SPEC.loader.exec_module(tool)


def _document() -> dict[str, object]:
    result = {
        "global_device_sample_start": 0,
        "sample_count": 2_500_000,
        "candidates": [
            {
                "qualified": True,
                "robust_z": 7.5,
                "frame_phase_samples": 1_000.0,
            }
        ],
        "windows": [
            {
                "fractional_global_device_sample": 1_000.25,
                "frame_phase_samples": 1_000.25,
            },
            {
                "fractional_global_device_sample": 4_333.5,
                "frame_phase_samples": 1_000.17,
            },
        ],
    }
    return {
        "analysis_kind": "candidate-only-rate-generic-pss-frame-timing-replay",
        "capture_id": "cap-test",
        "configuration": {"minimum_epoch_robust_z": 6.0},
        "targets": [
            {
                "stream_id": "stream-1",
                "receiver_id": 0,
                "sample_rate_hz": 2_500_000,
                "blocks": [{"block_index": 0, "result": result}],
            }
        ],
    }


def test_render_figures_produces_nonempty_pngs(tmp_path: Path) -> None:
    paths = tool.render_figures(
        _document(),
        first_sample_utc_ns={"stream-1": 1_000_000_000},
        output_directory=tmp_path,
        dpi=100,
    )

    assert [path.name for path in paths] == [
        "pss-detection-vs-time.png",
        "pss-frame-phase-vs-time.png",
    ]
    for path in paths:
        assert path.stat().st_size > 10_000
        payload = path.read_bytes()
        assert payload[:8] == b"\x89PNG\r\n\x1a\n"
        width, height = struct.unpack(">II", payload[16:24])
        assert width > height
