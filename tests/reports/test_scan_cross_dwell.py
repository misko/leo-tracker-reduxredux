from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np

PATH = (
    Path(__file__).resolve().parents[2]
    / "reports/2026_09_26_scan_fw_32a202b6e55630ec_phase_replay/cross-dwell/run.py"
)
SPEC = importlib.util.spec_from_file_location("scan_cross_dwell", PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_strict_causal_fit_excludes_overlapping_endpoint_support() -> None:
    rows = []
    for label, offset in ((10, 0.0), (11, 0.2)):
        for index in range(6):
            time = offset + index * 0.001
            rows.append((time, np.exp(2j * np.pi * 100 * time), label, 0.5))
    result = MODULE.fit(rows, 0)
    # Five left increments exist; the last two touch/overlap the held endpoint window.
    assert result["left_training_increment_count"] == 3
    assert result["joint_training_increment_count"] == 10
    assert result["strict_joint_training_increment_count"] == 6
    assert result["minimum_boundary_endpoint_coherence"] == 0.5
