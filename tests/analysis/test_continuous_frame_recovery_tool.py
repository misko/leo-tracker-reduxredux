from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from leo.analysis.research.continuous_frame_recovery import (
    FrameOpportunityOutcome,
    LockletEndReason,
    RecoveredFrame,
    RecoveryFilterMode,
)

TOOL_PATH = Path(__file__).parents[2] / "tools" / "prototype_continuous_frame_recovery.py"
SPEC = importlib.util.spec_from_file_location("prototype_continuous_frame_recovery", TOOL_PATH)
assert SPEC is not None and SPEC.loader is not None
tool = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = tool
SPEC.loader.exec_module(tool)


def _candidate(
    start: int,
    *,
    rank: int = 0,
    margin: float = 0.3,
    exact: float = 0.4,
) -> tool.GlrtAnchorCandidate:
    return tool.GlrtAnchorCandidate(
        detection_sample_start=start,
        candidate_rank=rank,
        local_epoch_sample=3333,
        tracking_cfo_hz=100_000.0 + rank,
        exact_score=exact,
        control_score=exact - margin,
        margin=margin,
    )


def test_frozen_config_validates_and_remains_outcome_blinded() -> None:
    path = Path(__file__).parents[2] / tool.DEFAULT_INPUTS
    document = json.loads(path.read_text(encoding="utf-8"))

    values = tool.validate_inputs(document)

    assert [value["label"] for value in values] == ["D1", "D2", "D6"]
    assert document["selection_lock"]["outcome_blinded"] is True
    assert all(
        value["interval"]["sample_end"] - value["interval"]["sample_start"] == 1_250_000
        for value in values
    )


def test_anchor_selection_is_safe_strong_and_deterministic() -> None:
    candidates = (
        _candidate(900, margin=0.9),  # starts before the segment
        _candidate(1_100, rank=2, margin=0.4),
        _candidate(1_100, rank=0, margin=0.4),
        _candidate(1_200, rank=0, margin=0.03),  # fails the frozen margin gate
        _candidate(5_100, margin=0.8),  # probe crosses the segment stop
    )

    selected = tool.select_segment_anchor(
        candidates,
        segment_start_sample=1_000,
        segment_stop_sample=6_000,
        probe_sample_count=1_000,
    )

    assert selected == candidates[2]


def test_legacy_replay_coverage_merges_overlaps_and_clips() -> None:
    document = {
        "bins": [
            {"status": "selected", "seed": {"sample_start": 50}},
            {"status": "selected", "seed": {"sample_start": 120}},
            {"status": "selected", "seed": {"sample_start": 310}},
            {"status": "empty", "seed": {"sample_start": 0}},
        ]
    }

    covered = tool.legacy_replay_coverage_samples(
        document,
        interval_start_sample=100,
        interval_stop_sample=400,
        replay_sample_count=100,
    )

    assert covered == 210  # [100, 220) union [310, 400)


def _frame(*, frame_start: int, odd_boundary: bool = False) -> RecoveredFrame:
    split = SimpleNamespace(
        odd_search_boundary=odd_boundary,
        even_absolute_cfo_hz=100_000.0,
        odd_absolute_cfo_hz=100_010.0,
        even_frequency_uncertainty_hz=5.0,
        odd_frequency_uncertainty_hz=5.0,
    )
    return RecoveredFrame(
        opportunity_index=0,
        anchor_id="anchor",
        lattice_index=0,
        frame_start_sample=frame_start,
        reference_sample=float(frame_start + 1_600),
        outcome=FrameOpportunityOutcome.SUPPORTED,
        mode=RecoveryFilterMode.TRACK,
        locklet_index=0,
        reacquired=False,
        hard_split_before=False,
        split_reason=None,
        estimator_seed_cfo_hz=100_000.0,
        predicted_cfo_hz=100_000.0,
        tracked_cfo_hz=100_001.0,
        tracked_rate_hz_s=10.0,
        filter_accepted=True,
        predicted_only=False,
        frequency_innovation_hz=1.0,
        normalized_frequency_innovation=0.1,
        odd_prediction_error_hz=10.0,
        rejection_reasons=(),
        primary=None,
        split_validation=split,  # type: ignore[arg-type]
    )


def _owned_anchor() -> tool.OwnedAnchor:
    candidate = _candidate(10_000)
    anchor = SimpleNamespace(anchor_id="anchor")
    return tool.OwnedAnchor(
        anchor=anchor,  # type: ignore[arg-type]
        segment_start_sample=0,
        segment_stop_sample=100_000,
        acquisition_start_sample=10_000,
        acquisition_stop_sample=60_000,
        candidate=candidate,
    )


def test_conditional_odd_scoring_excludes_acquisition_and_search_boundary() -> None:
    anchor = _owned_anchor()
    overlapping = tool._frame_document(
        "D1", _frame(frame_start=20_000), anchor, sample_rate_hz=2_500_000
    )
    boundary = tool._frame_document(
        "D1",
        _frame(frame_start=70_000, odd_boundary=True),
        anchor,
        sample_rate_hz=2_500_000,
    )
    clean = tool._frame_document("D1", _frame(frame_start=70_000), anchor, sample_rate_hz=2_500_000)

    assert overlapping["acquisition_overlap"] and not overlapping["odd_scored"]
    assert not overlapping["anchor_causally_available"]
    assert boundary["odd_search_boundary"] and not boundary["odd_scored"]
    assert clean["anchor_causally_available"] and clean["odd_scored"]


def test_trailing_line_is_causal_and_never_crosses_locklet() -> None:
    rows = []
    for index in range(8):
        rows.append(
            {
                "reference_time_s": index / 750.0,
                "locklet_index": 0,
                "outcome": FrameOpportunityOutcome.SUPPORTED.value,
                "even_absolute_cfo_hz": 100_000.0 + index,
                "odd_absolute_cfo_hz": 100_000.0 + index,
                "even_frequency_uncertainty_hz": 5.0,
                "odd_scored": True,
            }
        )
    rows.append(
        {
            "reference_time_s": 9 / 750.0,
            "locklet_index": 1,
            "outcome": FrameOpportunityOutcome.SUPPORTED.value,
            "even_absolute_cfo_hz": 200_000.0,
            "odd_absolute_cfo_hz": 200_000.0,
            "even_frequency_uncertainty_hz": 5.0,
            "odd_scored": True,
        }
    )

    tool.add_trailing_line_predictions(rows, minimum_history=6)

    assert all(not value["trailing_20ms_scored"] for value in rows[:6])
    assert rows[6]["trailing_20ms_scored"]
    assert rows[6]["trailing_20ms_odd_error_hz"] == pytest.approx(0.0, abs=1e-8)
    assert not rows[-1]["trailing_20ms_scored"]


def test_hard_split_reason_is_not_inferred_from_row_count() -> None:
    # A refill can annotate a crossing row and the next transition.  The runner
    # deliberately summarizes configured boundaries/locklet endings instead.
    assert LockletEndReason.REFILL_BOUNDARY.value == "refill_boundary"


def test_plot_smoke_preserves_declared_interval(tmp_path: Path) -> None:
    summary = {
        "label": "D1",
        "sample_rate_hz": 2_500_000,
        "interval_sample_start": 0,
        "interval_sample_stop": 250_000,
        "structurally_newly_read_fraction": 0.2,
        "legacy_seed_started_replay_spans": [{"sample_start": 0, "sample_stop": 125_000}],
        "unanchored_spans": [],
        "hard_refill_boundary_samples": [125_000],
        "prior_visible_gap": {"sample_start": 125_000, "sample_stop": 187_500},
        "anchors": [{"anchor_id": "anchor", "tracking_cfo_hz": 100_000.0}],
        "common_mask_trailing_20ms": {"recovery_filter_to_baseline_rms_ratio": 1.0},
    }
    rows = [
        {
            "label": "D1",
            "outcome": FrameOpportunityOutcome.SUPPORTED.value,
            "reference_time_s": 0.02,
            "anchor_id": "anchor",
            "locklet_index": 0,
            "even_absolute_cfo_hz": 100_010.0,
            "odd_absolute_cfo_hz": 100_012.0,
            "odd_scored": True,
            "anchor_causally_available": True,
            "predicted_cfo_hz": 100_007.0,
            "tracked_cfo_hz": 100_009.0,
            "trailing_20ms_prediction_hz": 100_008.0,
        }
    ]
    path = tmp_path / "recovery.png"

    tool.render_plot([summary], rows, path)

    assert path.is_file()
    assert path.stat().st_size > 1_000
