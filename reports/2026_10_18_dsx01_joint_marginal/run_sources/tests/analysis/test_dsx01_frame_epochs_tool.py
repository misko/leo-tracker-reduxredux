"""Frame coordinates preserve physical counters, fractional samples and IDs."""

import importlib
import sys
from pathlib import Path

import pytest


def test_frame_coordinate_uses_counter_fractional_epoch_and_physical_period():
    path = str(Path(__file__).resolve().parents[2] / "tools")
    sys.path.insert(0, path)
    try:
        tool = importlib.import_module("export_dsx01_frame_epochs")
    finally:
        sys.path.remove(path)
    peak = dict(
        passed_fractional_margin_gate=True,
        candidate_rank=0,
        fractional_margin=0.5,
        fractional_tracking_cfo_hz=123,
        integer_epoch_sample=3332,
        fractional_epoch_offset_samples=0.4,
    )
    probe = dict(
        receiver_id=0, channel=2, valid_start_counter=10000, probe_start_ms=20, candidates=[peak]
    )
    document = dict(
        source=dict(sample_rate_hz=2500000, probes=[probe]), clock_anchor=dict(sample_counter=1000)
    )
    scores = {
        "existing-id": dict(receiver=1, channel=2, valid_start_counter=10000, measured_cfo_hz=123)
    }
    row = tool.frame_epochs(document, scores)["existing-id"]
    expected = (9000 + 50000 + 3332.4) / 2500000
    assert row["frame_epoch_elapsed_s"] == pytest.approx(expected)
    assert row["frame_phase_modulo_s"] == pytest.approx(expected % (1 / 750))
    scores["existing-id"]["measured_cfo_hz"] = 124
    with pytest.raises(ValueError, match="CFO"):
        tool.frame_epochs(document, scores)
