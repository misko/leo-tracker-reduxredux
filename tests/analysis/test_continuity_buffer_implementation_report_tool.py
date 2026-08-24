from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from tools.report_continuity_buffer_implementation import render


def test_render_continuity_buffer_verification(tmp_path: Path) -> None:
    evidence = {
        "schema_version": 1,
        "controlled_131072_sample_refill": [
            {
                "kernel_buffers": value,
                "tested_boundaries": 10,
                "gap_boundaries": 10 if value == 1 else 0,
            }
            for value in (1, 2, 4, 8)
        ],
        "paired_60_second_dwell": {
            "legacy_recent_create_to_finalize_wall_seconds": 100.0,
            "create_to_finalize_wall_seconds": 62.0,
        },
        "scanner_eight_target": {
            "recent_v1_wall_seconds_range": [1.8, 2.0],
            "capture_wall_seconds": 5.7,
        },
    }
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    output = tmp_path / "figure.png"

    render(evidence_path, output)

    with Image.open(output) as image:
        assert image.format == "PNG"
        assert image.width >= 2000
        assert image.height >= 800
