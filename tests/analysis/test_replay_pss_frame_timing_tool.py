from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

TOOL_PATH = Path(__file__).parents[2] / "tools" / "replay_pss_frame_timing.py"
SPEC = importlib.util.spec_from_file_location("replay_pss_frame_timing", TOOL_PATH)
assert SPEC is not None and SPEC.loader is not None
tool = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = tool
SPEC.loader.exec_module(tool)


def test_target_and_frequency_bank_are_explicit_and_deterministic() -> None:
    assert tool._parse_target("stream-1:0") == tool.ReplayTarget("stream-1", 0)
    assert tool._frequency_bank(
        nominal_hz=50_000.0, half_width_hz=200_000.0, step_hz=100_000.0
    ) == (
        -150_000.0,
        -50_000.0,
        50_000.0,
        150_000.0,
        250_000.0,
    )
    with pytest.raises(ValueError, match="form"):
        tool._parse_target("stream-1")


def test_continuity_blocking_never_creates_an_insufficient_tail() -> None:
    blocks = tool._continuity_blocks(
        continuity_segment_index=4,
        device_sample_start=100,
        sample_count=2_050,
        maximum_block_samples=1_000,
        minimum_block_samples=100,
    )

    assert blocks == (
        tool.ReplayBlock(4, 100, 1_000),
        tool.ReplayBlock(4, 1_100, 1_050),
    )
    assert sum(block.sample_count for block in blocks) == 2_050
    assert all(block.continuity_segment_index == 4 for block in blocks)


def test_empty_persisted_continuity_segment_has_no_replay_block() -> None:
    assert (
        tool._continuity_blocks(
            continuity_segment_index=8,
            device_sample_start=40_000,
            sample_count=0,
            maximum_block_samples=1_000,
            minimum_block_samples=100,
        )
        == ()
    )


def test_qnap_output_is_explicitly_read_only() -> None:
    with pytest.raises(ValueError, match="read-only QNAP"):
        tool._validate_output_path(Path("/mnt/qnap01/analysis/pss.json"))
