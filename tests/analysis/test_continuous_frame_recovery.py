from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import numpy as np
import pytest

from leo.analysis.qam import PilotFrameCfoEstimate, PilotFrameCfoSplitValidation
from leo.analysis.research import continuous_frame_recovery as recovery
from leo.analysis.research.continuous_frame_recovery import (
    FrameOpportunityOutcome,
    FrameRecoveryAnchor,
    FrameRecoveryConfig,
    LockletEndReason,
    RecoveryFilterMode,
    anchors_compatible,
    recover_contiguous_frames,
)
from leo.analysis.starlink import NumericalStatus
from leo.analysis.starlink.templates import StarlinkEdge

RATE = 2_500_000
CAPTURE_START = 1_000_000
FIRST_FRAME = CAPTURE_START + 1


def _anchor(
    anchor_id: str = "anchor-0",
    *,
    first_frame: int = FIRST_FRAME,
    frame_count: int = 8,
    epoch_sample: int | None = None,
    source: str = "recording",
    alias: int = 0,
    edge: StarlinkEdge = StarlinkEdge.LOWER,
    cfo_hz: float = 100_000.0,
) -> FrameRecoveryAnchor:
    return FrameRecoveryAnchor(
        anchor_id=anchor_id,
        sample_source_id=source,
        canonical_observation_id=f"canonical-{anchor_id}",
        source_observation_id=f"source-{anchor_id}",
        edge=edge,
        cfo_alias_index=alias,
        epoch_sample=first_frame if epoch_sample is None else epoch_sample,
        acquisition_absolute_cfo_hz=cfo_hz,
        ownership_start_sample=first_frame,
        ownership_stop_sample=first_frame + round(frame_count * RATE / 750),
        continuity_source_id="candidate-1",
    )


def _primary(
    frame_start_sample: int,
    absolute_cfo_hz: float,
    *,
    supported: bool = True,
) -> PilotFrameCfoEstimate:
    return PilotFrameCfoEstimate(
        status=NumericalStatus.COMPLETE,
        measurement_supported=supported,
        rejection_reasons=() if supported else ("full_frame_rejected",),
        frame_start_sample=frame_start_sample,
        reference_sample=float(frame_start_sample + 1_600),
        residual_cfo_hz=0.0,
        absolute_cfo_hz=absolute_cfo_hz,
        frequency_uncertainty_hz=5.0,
        exact_coherence=0.5,
        control_coherence=0.01,
        coherence_margin=0.49,
        even_residual_cfo_hz=0.0,
        odd_residual_cfo_hz=0.0,
        even_odd_disagreement_hz=0.0,
        timing_spread_hz=0.0,
        half_frame_difference_z=0.0,
        tone_deletion_spread_hz=0.0,
        search_boundary=False,
    )


def _split(
    frame_start_sample: int,
    seed_hz: float,
    *,
    status: NumericalStatus = NumericalStatus.COMPLETE,
    supported: bool = True,
    even_absolute_hz: float = 100_000.0,
    odd_absolute_hz: float = 100_000.0,
) -> PilotFrameCfoSplitValidation:
    complete = status is NumericalStatus.COMPLETE
    return PilotFrameCfoSplitValidation(
        status=status,
        training_supported=complete and supported,
        training_rejection_reasons=(
            ()
            if complete and supported
            else ("zero_pilot_energy",)
            if status is NumericalStatus.NO_RESULT
            else ("even_exact_coherence_below_minimum",)
        ),
        frame_start_sample=frame_start_sample,
        reference_sample=float(frame_start_sample + 1_600),
        even_residual_cfo_hz=even_absolute_hz - seed_hz if complete else None,
        odd_residual_cfo_hz=odd_absolute_hz - seed_hz if complete else None,
        even_absolute_cfo_hz=even_absolute_hz if complete else None,
        odd_absolute_cfo_hz=odd_absolute_hz if complete else None,
        even_frequency_uncertainty_hz=5.0 if complete else None,
        odd_frequency_uncertainty_hz=5.0 if complete else None,
        even_exact_coherence=0.5 if complete else None,
        even_control_coherence=0.01 if complete else None,
        even_coherence_margin=0.49 if complete else None,
        even_search_boundary=False,
        odd_search_boundary=False,
    )


def _install_estimators(
    monkeypatch: pytest.MonkeyPatch,
    split_factory: Callable[[int, float], PilotFrameCfoSplitValidation],
    *,
    primary_supported: bool = True,
) -> list[int]:
    calls: list[int] = []

    def primary(
        samples: np.ndarray,
        sample_rate_hz: float,
        *,
        frame_start_sample: int,
        acquisition_absolute_cfo_hz: float,
        edge: StarlinkEdge | str,
        config: object,
    ) -> PilotFrameCfoEstimate:
        del samples, sample_rate_hz, edge, config
        calls.append(frame_start_sample)
        return _primary(
            frame_start_sample,
            acquisition_absolute_cfo_hz,
            supported=primary_supported,
        )

    def split(
        samples: np.ndarray,
        sample_rate_hz: float,
        *,
        frame_start_sample: int,
        acquisition_absolute_cfo_hz: float,
        edge: StarlinkEdge | str,
        config: object,
    ) -> PilotFrameCfoSplitValidation:
        del samples, sample_rate_hz, edge, config
        return split_factory(frame_start_sample, acquisition_absolute_cfo_hz)

    monkeypatch.setattr(recovery, "estimate_edge_pilot_frame_cfo", primary)
    monkeypatch.setattr(recovery, "estimate_edge_pilot_frame_cfo_split_validation", split)
    return calls


def _samples(stop_sample: int) -> np.ndarray:
    return np.ones(stop_sample - CAPTURE_START, dtype=np.complex64)


def test_anchor_projects_exact_lattice_backward_and_accounts_unowned_samples(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame_count = 8
    late_epoch = FIRST_FRAME + round(4 * RATE / 750)
    anchor = _anchor(frame_count=frame_count, epoch_sample=late_epoch)
    anchor = replace(
        anchor,
        ownership_stop_sample=late_epoch + round(4 * RATE / 750),
    )
    calls = _install_estimators(
        monkeypatch,
        lambda start, seed: _split(start, seed),
    )

    result = recover_contiguous_frames(
        _samples(anchor.ownership_stop_sample),
        sample_start=CAPTURE_START,
        sample_rate_hz=RATE,
        anchors=(anchor,),
    )

    expected = tuple(late_epoch + round(index * RATE / 750) for index in range(-4, 4))
    assert tuple(frame.frame_start_sample for frame in result.frames) == expected
    assert tuple(frame.lattice_index for frame in result.frames) == tuple(range(-4, 4))
    assert set(np.diff(expected)) == {3333, 3334}
    assert calls == list(expected)
    assert result.unanchored_spans == (recovery.UnanchoredSampleSpan(CAPTURE_START, FIRST_FRAME),)
    assert result.accounted_sample_count == anchor.ownership_stop_sample - FIRST_FRAME
    assert all(frame.outcome is FrameOpportunityOutcome.SUPPORTED for frame in result.frames)


def test_short_coast_expires_then_supported_frame_reacquires(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    anchor = _anchor(frame_count=6)
    disposition = {
        FIRST_FRAME: (NumericalStatus.COMPLETE, True),
        FIRST_FRAME + round(RATE / 750): (NumericalStatus.NO_RESULT, False),
        FIRST_FRAME + round(2 * RATE / 750): (NumericalStatus.COMPLETE, False),
        FIRST_FRAME + round(3 * RATE / 750): (NumericalStatus.NO_RESULT, False),
    }

    def split_factory(start: int, seed: float) -> PilotFrameCfoSplitValidation:
        status, supported = disposition.get(start, (NumericalStatus.COMPLETE, True))
        return _split(start, seed, status=status, supported=supported)

    _install_estimators(monkeypatch, split_factory)
    result = recover_contiguous_frames(
        _samples(anchor.ownership_stop_sample),
        sample_start=CAPTURE_START,
        sample_rate_hz=RATE,
        anchors=(anchor,),
        config=FrameRecoveryConfig(maximum_coast_frames=2),
    )

    assert tuple(frame.outcome for frame in result.frames[:4]) == (
        FrameOpportunityOutcome.SUPPORTED,
        FrameOpportunityOutcome.ESTIMATOR_NO_RESULT,
        FrameOpportunityOutcome.REJECTED,
        FrameOpportunityOutcome.ESTIMATOR_NO_RESULT,
    )
    assert tuple(frame.predicted_only for frame in result.frames[:4]) == (
        False,
        True,
        True,
        False,
    )
    assert result.frames[1].mode is result.frames[2].mode is RecoveryFilterMode.COAST
    assert result.frames[3].locklet_index is None
    assert result.frames[3].mode is RecoveryFilterMode.LOST
    assert result.frames[4].reacquired
    assert len(result.locklets) == 2
    assert result.locklets[0].predicted_only_frame_count == 2
    assert result.locklets[0].ended_by is LockletEndReason.COAST_EXPIRED
    assert result.locklets[1].reacquired


def test_odd_qin_is_held_out_from_selection_and_filter_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    anchor = _anchor(frame_count=5)

    def execute(odd_offset_hz: float) -> recovery.ContinuousFrameRecoveryResult:
        _install_estimators(
            monkeypatch,
            lambda start, seed: _split(
                start,
                seed,
                even_absolute_hz=100_000.0,
                odd_absolute_hz=100_000.0 + odd_offset_hz,
            ),
            primary_supported=False,
        )
        return recover_contiguous_frames(
            _samples(anchor.ownership_stop_sample),
            sample_start=CAPTURE_START,
            sample_rate_hz=RATE,
            anchors=(anchor,),
        )

    agreeing = execute(0.0)
    corrupted_odd = execute(50_000.0)

    assert all(frame.outcome is FrameOpportunityOutcome.SUPPORTED for frame in corrupted_odd.frames)
    assert all(frame.filter_accepted for frame in corrupted_odd.frames)
    assert all(
        frame.primary is not None and not frame.primary.measurement_supported
        for frame in corrupted_odd.frames
    )
    assert tuple(frame.tracked_cfo_hz for frame in corrupted_odd.frames) == tuple(
        frame.tracked_cfo_hz for frame in agreeing.frames
    )
    assert tuple(frame.locklet_index for frame in corrupted_odd.frames) == tuple(
        frame.locklet_index for frame in agreeing.frames
    )
    assert all(
        frame.odd_prediction_error_hz == pytest.approx(50_000.0)
        for frame in corrupted_odd.frames[1:]
    )


def test_refill_crossing_is_explicit_and_hard_splits_locklets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    anchor = _anchor(frame_count=7)
    _install_estimators(monkeypatch, lambda start, seed: _split(start, seed))
    crossing_start = FIRST_FRAME + round(3 * RATE / 750)
    refill = crossing_start + 500

    result = recover_contiguous_frames(
        _samples(anchor.ownership_stop_sample),
        sample_start=CAPTURE_START,
        sample_rate_hz=RATE,
        anchors=(anchor,),
        refill_boundaries=(refill,),
    )

    crossing = result.frames[3]
    assert crossing.outcome is FrameOpportunityOutcome.CROSSES_REFILL_BOUNDARY
    assert crossing.primary is crossing.split_validation is None
    assert crossing.hard_split_before
    assert crossing.split_reason is LockletEndReason.REFILL_BOUNDARY
    assert result.frames[4].reacquired
    assert not result.frames[4].hard_split_before
    assert len(result.locklets) == 2
    assert result.locklets[0].ended_by is LockletEndReason.REFILL_BOUNDARY


def test_alias_change_and_unanchored_gap_cannot_share_a_locklet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _anchor("first", frame_count=3)
    second_start = first.ownership_stop_sample
    compatible = _anchor("compatible", first_frame=second_start, frame_count=3)
    assert anchors_compatible(first, compatible, sample_rate_hz=RATE)
    assert not anchors_compatible(
        first,
        replace(compatible, continuity_source_id=None, cfo_alias_index=None),
        sample_rate_hz=RATE,
    )
    second = _anchor(
        "second",
        first_frame=second_start,
        frame_count=3,
        alias=1,
        cfo_hz=327_272.727,
    )
    _install_estimators(monkeypatch, lambda start, seed: _split(start, seed, even_absolute_hz=seed))

    assert not anchors_compatible(first, second, sample_rate_hz=RATE)
    result = recover_contiguous_frames(
        _samples(second.ownership_stop_sample),
        sample_start=CAPTURE_START,
        sample_rate_hz=RATE,
        anchors=(first, second),
    )

    boundary_rows = [
        frame
        for frame in result.frames
        if frame.outcome is FrameOpportunityOutcome.CROSSES_INCOMPATIBLE_ANCHOR
    ]
    assert boundary_rows
    assert all(
        frame.split_reason is LockletEndReason.ANCHOR_ALIAS_CHANGED for frame in boundary_rows
    )
    assert len(result.locklets) == 2
    assert result.locklets[0].ended_by is LockletEndReason.ANCHOR_ALIAS_CHANGED
    assert result.locklets[1].reacquired

    gap = round(2 * RATE / 750)
    separated = _anchor(
        "separated",
        first_frame=first.ownership_stop_sample + gap,
        frame_count=2,
    )
    gap_result = recover_contiguous_frames(
        _samples(separated.ownership_stop_sample),
        sample_start=CAPTURE_START,
        sample_rate_hz=RATE,
        anchors=(first, separated),
    )
    assert gap_result.unanchored_spans[-1] == recovery.UnanchoredSampleSpan(
        first.ownership_stop_sample,
        separated.ownership_start_sample,
    )
    first_separated = next(frame for frame in gap_result.frames if frame.anchor_id == "separated")
    assert first_separated.hard_split_before
    assert first_separated.split_reason is LockletEndReason.UNANCHORED_GAP


def test_invalid_anchor_overlap_and_refill_geometry_fail_closed() -> None:
    first = _anchor("first", frame_count=3)
    overlapping = _anchor(
        "overlap",
        first_frame=first.ownership_stop_sample - 10,
        frame_count=2,
    )
    samples = _samples(overlapping.ownership_stop_sample)

    with pytest.raises(ValueError, match="must not overlap"):
        recover_contiguous_frames(
            samples,
            sample_start=CAPTURE_START,
            sample_rate_hz=RATE,
            anchors=(first, overlapping),
        )
    with pytest.raises(ValueError, match="strictly inside"):
        recover_contiguous_frames(
            samples,
            sample_start=CAPTURE_START,
            sample_rate_hz=RATE,
            anchors=(first,),
            refill_boundaries=(CAPTURE_START,),
        )
