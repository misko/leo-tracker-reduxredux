from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from tools.report_continuity_buffer_implementation import render


def test_render_continuity_buffer_verification(tmp_path: Path) -> None:
    evidence = {
        "schema_version": 2,
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
        },
        "scanner_eight_target": {
            "recent_v1_wall_seconds_range": [1.8, 2.0],
        },
        "post_deploy_paired_60_second_dwell": {
            "create_to_finalize_wall_seconds": 63.0,
            "verified_counter_boundaries": [572, 572],
            "counter_boundaries_per_radio": 572,
        },
        "post_deploy_scanner_four_sweep": {
            "capture_elapsed_seconds": [6.5, 6.6, 7.0, 7.2],
            "attested_target_frames": 32,
            "sweep_count": 4,
            "targets_per_sweep": 8,
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
