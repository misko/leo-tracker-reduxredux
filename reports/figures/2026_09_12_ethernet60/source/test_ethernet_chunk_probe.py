import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "ethernet_chunk_probe", Path(__file__).parents[1] / "tools" / "ethernet_chunk_probe.py"
)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def frame(first, end, missing=0, overflow=False):
    return dict(first=first, end=end, missing_before=missing, overflow=overflow)


def test_runs_and_coverage_do_not_bridge_gaps_or_count_unobserved_prefix():
    result = probe.summarize(
        [
            frame(100, 110, missing=90),
            frame(110, 120),
            frame(150, 160, missing=30, overflow=True),
        ],
        10,
    )
    assert result["source_coverage_fraction"] == 0.5
    assert result["longest_contiguous_seconds"] == 2
    assert result["prefix_missing_samples"] == 90
    assert result["internal_missing_samples"] == 30
    assert result["gap_count"] == 1
    assert result["overflow_frames"] == 1


@pytest.mark.parametrize("second", [frame(9, 19), frame(11, 21), frame(11, 21, 2)])
def test_rejects_overlap_and_unclosed_metadata(second):
    with pytest.raises(ValueError, match="counters"):
        probe.summarize([frame(0, 10), second], 10)


def test_a_single_continuous_block_is_a_lower_bound_on_possible_chunk():
    result = probe.summarize([frame(300, 340)], 20)
    assert result["longest_contiguous_seconds"] == 2
    assert result["source_coverage_fraction"] == 1
    assert result["gap_count"] == 0
