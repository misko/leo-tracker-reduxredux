from __future__ import annotations

import importlib.util
from pathlib import Path

_PATH = Path("tools/summarize_405bcc_track_loss.py")
_SPEC = importlib.util.spec_from_file_location("summarize_405bcc_track_loss", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def test_replay_allows_bounded_harmful_tail_but_final_fallback_requires_zero() -> None:
    row = {
        "tier": "geometry_only",
        "geometry_display_eligible": True,
        "evaluated_probe_count": 304,
        "evaluated_block_count": 9,
        "block_coverage_ratio": 1.0,
        "median_block_corrected_margin": 0.0051,
        "harmful_block_count": 2,
        "maximum_consecutive_harmful_blocks": 1,
    }
    replay_gate = {
        "minimum_probe_count": 20,
        "minimum_block_coverage_ratio": 0.5,
        "minimum_median_corrected_margin": 0.05,
        "maximum_harmful_block_fraction": 0.25,
        "maximum_consecutive_harmful_blocks": 2,
    }
    selection = {"minimum_corrected_margin": 0.0025}

    replay = _MODULE._replay_gate_facts(row, replay_gate)
    fallback = _MODULE._final_fallback_gate_facts(row, replay_gate, selection)

    assert replay["harmful_fraction"]
    assert replay["harmful_run"]
    assert not replay["minimum_corrected_margin"]
    assert fallback["minimum_corrected_margin"]
    assert not fallback["zero_harmful_blocks"]
    assert not fallback["zero_maximum_harmful_run"]


def test_nonharmful_weak_replay_geometry_passes_display_fallback_floor() -> None:
    row = {
        "tier": "geometry_only",
        "geometry_display_eligible": True,
        "evaluated_probe_count": 201,
        "block_coverage_ratio": 1.0,
        "median_block_corrected_margin": 0.0036,
        "harmful_block_count": 0,
        "maximum_consecutive_harmful_blocks": 0,
    }
    replay_gate = {"minimum_probe_count": 20, "minimum_block_coverage_ratio": 0.5}
    selection = {"minimum_corrected_margin": 0.0025}

    assert all(_MODULE._final_fallback_gate_facts(row, replay_gate, selection).values())
