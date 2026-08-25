from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

import leo.analysis.qam as public_qam
import leo.analysis.qam.pilot_pnt_kalman_v4 as v4_module
import leo.analysis.starlink as public_starlink
import leo.analysis.starlink.seeded_acquisition as seeded_module
from leo.analysis.qam.pilot_pnt_kalman import (
    PilotPntKalmanConfigV3,
    PilotPntKalmanResult,
    analyze_contiguous_pilot_pnt_kalman,
)
from leo.analysis.qam.pilot_pnt_kalman_v4 import (
    PilotPntKalmanConfigV4,
    PilotPntKalmanV4ModeResult,
    PilotPntKalmanV4PiecewiseResult,
    PilotPntKalmanV4Result,
    PilotPntKalmanV4SegmentSeed,
    analyze_contiguous_pilot_pnt_kalman_v4,
    analyze_piecewise_pilot_pnt_kalman_v4,
)
from leo.analysis.starlink.acquisition import NumericalStatus
from leo.analysis.starlink.seeded_acquisition import KnownPilotModeSeed
from leo.analysis.starlink.templates import FRAME_RATE_HZ, StarlinkEdge, qin_edge_pilot_frame

RATE = 2_500_000.0
EPOCH = 37


def _seed() -> KnownPilotModeSeed:
    return KnownPilotModeSeed(
        nominal_epoch_sample=EPOCH,
        nominal_absolute_cfo_hz=0.0,
        branch_id="fixture-branch",
        provenance_sha256="1" * 64,
    )


def _additional_seed() -> KnownPilotModeSeed:
    return KnownPilotModeSeed(
        nominal_epoch_sample=EPOCH,
        nominal_absolute_cfo_hz=85_000.0,
        branch_id="fixture-second-branch",
        provenance_sha256="2" * 64,
    )


def _capture(*, frame_count: int, cfo_hz: float) -> np.ndarray:
    template = qin_edge_pilot_frame(RATE, StarlinkEdge.LOWER)
    indexes = np.arange(template.size)
    final_start = EPOCH + round((frame_count - 1) * RATE / FRAME_RATE_HZ)
    samples = np.zeros(final_start + template.size + 2, dtype=np.complex128)
    for frame_index in range(frame_count):
        start = EPOCH + round(frame_index * RATE / FRAME_RATE_HZ)
        time_s = (start + indexes) / RATE
        phase = 0.3 + np.pi * (frame_index % 2) + 2 * np.pi * cfo_hz * time_s
        samples[start + indexes] += template * np.exp(1j * phase)
    return samples


def _tracking(
    status: NumericalStatus,
    *,
    phase_lock_qualified: bool = False,
) -> PilotPntKalmanResult:
    return PilotPntKalmanResult(
        status=status,
        frames=(),
        supported_frame_count=0,
        phase_update_count=0,
        frequency_update_count=0,
        timing_update_count=0,
        reacquisition_count=0,
        rate_bootstrap_frame_index=None,
        phase_lock_qualified=phase_lock_qualified,
        phase_lock_reason=(
            "qualified modulo-pi phase lock"
            if phase_lock_qualified
            else "no supported pilot frames"
        ),
        phase_ambiguity_transition_count=0,
        reason="test tracking outcome",
    )


def _mode(
    epoch_sample: int,
    absolute_cfo_hz: float,
    doppler_rate_hz_s: float = 0.0,
) -> SimpleNamespace:
    return SimpleNamespace(
        epoch_sample=epoch_sample,
        absolute_cfo_hz=absolute_cfo_hz,
        doppler_rate_hz_s=doppler_rate_hz_s,
    )


def _acquisition(
    *modes: SimpleNamespace,
    status: NumericalStatus = NumericalStatus.COMPLETE,
    **decisions: bool,
) -> SimpleNamespace:
    return SimpleNamespace(
        status=status,
        retained_modes=tuple(modes),
        accepted_modes=tuple(modes),
        **decisions,
    )


@pytest.mark.parametrize(
    "name",
    (
        "CFO_ALIAS_SPACING_HZ",
        "DEFAULT_CONDITIONAL_CONTROL_ROLLS",
        "PER_SUBCARRIER_DERANGEMENT_ROLLS",
        "KnownPilotBlockEvidence",
        "KnownPilotModeCandidate",
        "KnownPilotModeSeed",
        "PilotModeProposalOrigin",
        "PilotTemplateIdentity",
        "ResearchDisposition",
        "ResearchEvidenceDecision",
        "SeededPilotAcquisitionConfig",
        "SeededPilotAcquisitionResult",
        "TemplateEvidenceRole",
        "acquire_seeded_known_pilot_modes",
        "canonicalize_cfo_alias",
    ),
)
def test_seeded_acquisition_research_api_is_public(name: str) -> None:
    assert name in public_starlink.__all__
    assert getattr(public_starlink, name) is getattr(seeded_module, name)


@pytest.mark.parametrize(
    "name",
    (
        "PilotPntKalmanConfigV4",
        "PilotPntKalmanV4ModeResult",
        "PilotPntKalmanV4PiecewiseResult",
        "PilotPntKalmanV4Result",
        "PilotPntKalmanV4SegmentResult",
        "PilotPntKalmanV4SegmentSeed",
        "analyze_contiguous_pilot_pnt_kalman_v4",
        "analyze_piecewise_pilot_pnt_kalman_v4",
    ),
)
def test_pnt_kalman_v4_research_api_is_public(name: str) -> None:
    assert name in public_qam.__all__
    assert getattr(public_qam, name) is getattr(v4_module, name)


def test_v4_runs_one_unchanged_independent_tracker_per_accepted_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    modes = (_mode(19, 81_250.0, -2_100.0), _mode(731, 166_100.0, 3_400.0))
    acquisition = _acquisition(*modes)
    acquisition_calls = []
    tracking_calls = []
    outcomes = iter(
        (
            _tracking(NumericalStatus.COMPLETE),
            _tracking(NumericalStatus.COMPLETE, phase_lock_qualified=True),
        )
    )

    def fake_acquire(*args: object, **kwargs: object) -> SimpleNamespace:
        acquisition_calls.append((args, kwargs))
        return acquisition

    def fake_track(*args: object, **kwargs: object) -> PilotPntKalmanResult:
        tracking_calls.append((args, kwargs))
        return next(outcomes)

    monkeypatch.setattr(v4_module, "acquire_seeded_known_pilot_modes", fake_acquire)
    monkeypatch.setattr(v4_module, "analyze_contiguous_pilot_pnt_kalman", fake_track)
    samples = np.ones(20_000, dtype=np.complex64)
    seed = _seed()
    additional_seed = _additional_seed()
    settings = PilotPntKalmanConfigV4()

    result = analyze_contiguous_pilot_pnt_kalman_v4(
        samples,
        RATE,
        seed=seed,
        additional_seeds=(additional_seed,),
        edge=StarlinkEdge.UPPER,
        maximum_residual_cfo_hz=1_500.0,
        config=settings,
    )

    assert result.numerical_status is NumericalStatus.COMPLETE
    assert result.acquisition is acquisition
    assert tuple(row.mode for row in result.mode_results) == modes
    assert result.complete_mode_count == 2
    assert result.phase_lock_qualified_mode_count == 1
    assert result.candidate_only
    assert not result.standard_pipeline
    assert len(acquisition_calls) == 1
    assert acquisition_calls[0][1]["seed"] is seed
    assert acquisition_calls[0][1]["additional_seeds"] == (additional_seed,)
    assert acquisition_calls[0][1]["config"] is settings.acquisition_config
    assert len(tracking_calls) == 2
    assert tracking_calls[0][0][0] is tracking_calls[1][0][0]
    assert [call[1]["epoch_sample"] for call in tracking_calls] == [19, 731]
    assert [call[1]["initial_absolute_cfo_hz"] for call in tracking_calls] == [
        81_250.0,
        166_100.0,
    ]
    assert [call[1]["config"].initial_doppler_rate_hz_s for call in tracking_calls] == [
        -2_100.0,
        3_400.0,
    ]
    assert [
        replace(call[1]["config"], initial_doppler_rate_hz_s=0.0) for call in tracking_calls
    ] == [settings.tracker_config, settings.tracker_config]
    assert all(call[1]["maximum_residual_cfo_hz"] == 1_500.0 for call in tracking_calls)


def test_v4_mode_track_matches_direct_core_with_mode_specific_initial_rate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mode = _mode(EPOCH, 0.0, 1_250.0)
    acquisition = _acquisition(mode)
    monkeypatch.setattr(
        v4_module,
        "acquire_seeded_known_pilot_modes",
        lambda *args, **kwargs: acquisition,
    )
    samples = _capture(frame_count=40, cfo_hz=0.0)
    settings = PilotPntKalmanConfigV4()

    result = analyze_contiguous_pilot_pnt_kalman_v4(
        samples,
        RATE,
        seed=_seed(),
        edge=StarlinkEdge.LOWER,
        config=settings,
    )
    expected = analyze_contiguous_pilot_pnt_kalman(
        samples,
        RATE,
        epoch_sample=EPOCH,
        initial_absolute_cfo_hz=0.0,
        edge=StarlinkEdge.LOWER,
        config=replace(
            settings.tracker_config,
            initial_doppler_rate_hz_s=mode.doppler_rate_hz_s,
        ),
    )

    assert result.mode_results[0].tracking == expected


def test_v4_does_not_conflate_acquisition_decisions_tracking_and_phase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mode = _mode(EPOCH, 40_000.0)
    acquisition = _acquisition(
        mode,
        status=NumericalStatus.COMPLETE,
        specificity_claimed=False,
        thresholds_calibrated=False,
    )
    monkeypatch.setattr(
        v4_module,
        "acquire_seeded_known_pilot_modes",
        lambda *args, **kwargs: acquisition,
    )
    monkeypatch.setattr(
        v4_module,
        "analyze_contiguous_pilot_pnt_kalman",
        lambda *args, **kwargs: _tracking(
            NumericalStatus.COMPLETE,
            phase_lock_qualified=True,
        ),
    )

    result = analyze_contiguous_pilot_pnt_kalman_v4(
        np.ones(20_000, dtype=np.complex128),
        RATE,
        seed=_seed(),
        edge=StarlinkEdge.LOWER,
    )

    assert result.numerical_status is NumericalStatus.COMPLETE
    assert result.acquisition.status is NumericalStatus.COMPLETE
    assert not result.acquisition.specificity_claimed
    assert not result.acquisition.thresholds_calibrated
    assert result.phase_lock_qualified_mode_count == 1
    assert result.mode_results[0].phase_lock_qualified


def test_v4_keeps_rejected_retained_proposals_out_of_tracking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    accepted = _mode(17, 25_000.0)
    rejected = _mode(901, -130_000.0)
    acquisition = SimpleNamespace(
        status=NumericalStatus.COMPLETE,
        retained_modes=(accepted, rejected),
        accepted_modes=(accepted,),
    )
    tracked_epochs = []
    monkeypatch.setattr(
        v4_module,
        "acquire_seeded_known_pilot_modes",
        lambda *args, **kwargs: acquisition,
    )

    def fake_track(*args: object, **kwargs: object) -> PilotPntKalmanResult:
        tracked_epochs.append(kwargs["epoch_sample"])
        return _tracking(NumericalStatus.COMPLETE)

    monkeypatch.setattr(v4_module, "analyze_contiguous_pilot_pnt_kalman", fake_track)

    result = analyze_contiguous_pilot_pnt_kalman_v4(
        np.ones(20_000),
        RATE,
        seed=_seed(),
        edge=StarlinkEdge.LOWER,
    )

    assert tracked_epochs == [accepted.epoch_sample]
    assert result.acquisition.retained_modes == (accepted, rejected)
    assert tuple(row.mode for row in result.mode_results) == (accepted,)


@pytest.mark.parametrize(
    ("outcomes", "expected"),
    (
        (
            (NumericalStatus.COMPLETE, NumericalStatus.NO_RESULT),
            NumericalStatus.INSUFFICIENT,
        ),
        (
            (NumericalStatus.INSUFFICIENT, NumericalStatus.NO_RESULT),
            NumericalStatus.INSUFFICIENT,
        ),
        (
            (NumericalStatus.NO_RESULT, NumericalStatus.NO_RESULT),
            NumericalStatus.NO_RESULT,
        ),
    ),
)
def test_v4_reports_partial_and_failed_numerical_outcomes_without_dropping_modes(
    monkeypatch: pytest.MonkeyPatch,
    outcomes: tuple[NumericalStatus, NumericalStatus],
    expected: NumericalStatus,
) -> None:
    acquisition = _acquisition(_mode(10, 1_000.0), _mode(20, 2_000.0))
    iterator = iter(_tracking(status) for status in outcomes)
    monkeypatch.setattr(
        v4_module,
        "acquire_seeded_known_pilot_modes",
        lambda *args, **kwargs: acquisition,
    )
    monkeypatch.setattr(
        v4_module,
        "analyze_contiguous_pilot_pnt_kalman",
        lambda *args, **kwargs: next(iterator),
    )

    result = analyze_contiguous_pilot_pnt_kalman_v4(
        np.ones(20_000),
        RATE,
        seed=_seed(),
        edge=StarlinkEdge.LOWER,
    )

    assert result.numerical_status is expected
    assert len(result.mode_results) == 2
    assert tuple(row.numerical_status for row in result.mode_results) == outcomes


def test_v4_propagates_insufficient_acquisition_without_calling_tracker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    acquisition = _acquisition(status=NumericalStatus.INSUFFICIENT)
    monkeypatch.setattr(
        v4_module,
        "acquire_seeded_known_pilot_modes",
        lambda *args, **kwargs: acquisition,
    )

    def forbidden_tracker(*args: object, **kwargs: object) -> PilotPntKalmanResult:
        raise AssertionError("tracker must not run without a retained mode")

    monkeypatch.setattr(v4_module, "analyze_contiguous_pilot_pnt_kalman", forbidden_tracker)
    result = analyze_contiguous_pilot_pnt_kalman_v4(
        np.ones(20_000),
        RATE,
        seed=_seed(),
        edge=StarlinkEdge.LOWER,
    )

    assert result.numerical_status is NumericalStatus.INSUFFICIENT
    assert result.mode_results == ()
    assert result.complete_mode_count == 0
    assert result.phase_lock_qualified_mode_count == 0


def test_v4_requires_the_unchanged_phase_safe_v3_policy() -> None:
    with pytest.raises(ValueError, match="phase-safe V3"):
        PilotPntKalmanConfigV4(
            tracker_config=PilotPntKalmanConfigV3(decouple_phase_from_frequency=False)
        )


def test_v4_result_counts_are_checked() -> None:
    acquisition = _acquisition(_mode(EPOCH, 0.0))
    with pytest.raises(ValueError, match="complete-mode count"):
        PilotPntKalmanV4Result(
            numerical_status=NumericalStatus.COMPLETE,
            acquisition=acquisition,  # type: ignore[arg-type]
            mode_results=(),
            complete_mode_count=1,
            phase_lock_qualified_mode_count=0,
            reason="invalid fixture",
        )


def test_v4_fixed_mode_tracking_is_identical_to_the_v3_core(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame_count = 30
    cfo_hz = 51_250.0
    samples = _capture(frame_count=frame_count, cfo_hz=cfo_hz)

    acquisition = _acquisition(_mode(EPOCH, cfo_hz))
    monkeypatch.setattr(
        v4_module,
        "acquire_seeded_known_pilot_modes",
        lambda *args, **kwargs: acquisition,
    )
    tracker_config = PilotPntKalmanConfigV3(timing_innovation_gate_sigma=100.0)
    settings = PilotPntKalmanConfigV4(tracker_config=tracker_config)

    result = analyze_contiguous_pilot_pnt_kalman_v4(
        samples,
        RATE,
        seed=_seed(),
        edge=StarlinkEdge.LOWER,
        config=settings,
    )
    direct = analyze_contiguous_pilot_pnt_kalman(
        samples,
        RATE,
        epoch_sample=EPOCH,
        initial_absolute_cfo_hz=cfo_hz,
        edge=StarlinkEdge.LOWER,
        config=tracker_config,
    )

    assert result.mode_results[0].tracking == direct
    assert result.mode_results[0].tracking.status is NumericalStatus.COMPLETE
    assert result.mode_results[0].tracking.phase_lock_qualified == direct.phase_lock_qualified


def test_v4_integrates_the_real_seeded_acquisition_contract() -> None:
    cfo_hz = 51_250.0
    samples = _capture(frame_count=56, cfo_hz=cfo_hz)
    seed = KnownPilotModeSeed(
        nominal_epoch_sample=EPOCH,
        nominal_absolute_cfo_hz=cfo_hz,
        branch_id="exact-integration-fixture",
        provenance_sha256="2" * 64,
    )

    result = analyze_contiguous_pilot_pnt_kalman_v4(
        samples,
        RATE,
        seed=seed,
        edge=StarlinkEdge.LOWER,
    )

    assert result.acquisition.status is NumericalStatus.COMPLETE
    assert result.acquisition.accepted_modes
    assert len(result.mode_results) == len(result.acquisition.accepted_modes)
    assert result.complete_mode_count == len(result.mode_results)
    assert result.numerical_status is NumericalStatus.COMPLETE


def test_piecewise_v4_runs_fresh_segment_local_calls_and_accounts_outcomes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primary_a = KnownPilotModeSeed(11, 1_000.0, "segment-a", "a" * 64)
    primary_b = KnownPilotModeSeed(29, 2_000.0, "segment-b", "b" * 64)
    secondary_b = KnownPilotModeSeed(31, 87_000.0, "segment-b-alt", "c" * 64)
    segments = (
        PilotPntKalmanV4SegmentSeed(0, 100, primary_a),
        PilotPntKalmanV4SegmentSeed(150, 350, primary_b, (secondary_b,)),
    )
    samples = np.arange(400, dtype=np.complex128) + 1j
    calls = []

    def fake_contiguous(
        segment_samples: np.ndarray,
        sample_rate_hz: float,
        **kwargs: object,
    ) -> PilotPntKalmanV4Result:
        calls.append((segment_samples, sample_rate_hz, kwargs))
        phase_lock = len(calls) == 2
        mode_result = PilotPntKalmanV4ModeResult(
            mode=_mode(11 if len(calls) == 1 else 29, 1_000.0),
            tracking=_tracking(
                NumericalStatus.COMPLETE,
                phase_lock_qualified=phase_lock,
            ),
        )
        return PilotPntKalmanV4Result(
            numerical_status=NumericalStatus.COMPLETE,
            acquisition=_acquisition(mode_result.mode),  # type: ignore[arg-type]
            mode_results=(mode_result,),
            complete_mode_count=1,
            phase_lock_qualified_mode_count=int(phase_lock),
            reason="fresh segment fixture",
        )

    monkeypatch.setattr(
        v4_module,
        "analyze_contiguous_pilot_pnt_kalman_v4",
        fake_contiguous,
    )
    settings = PilotPntKalmanConfigV4()
    result = analyze_piecewise_pilot_pnt_kalman_v4(
        samples,
        RATE,
        segments=segments,
        edge=StarlinkEdge.UPPER,
        maximum_residual_cfo_hz=1_250.0,
        expected_symbol_roll=0,
        config=settings,
    )

    assert isinstance(result, PilotPntKalmanV4PiecewiseResult)
    assert result.numerical_status is NumericalStatus.COMPLETE
    assert result.complete_segment_count == 2
    assert result.complete_mode_count == 2
    assert result.phase_lock_qualified_mode_count == 1
    assert result.reacquisition_count == 1
    assert result.candidate_only
    assert not result.standard_pipeline
    assert tuple(row.segment for row in result.segments) == segments
    assert len(calls) == 2
    assert calls[0][0] is not calls[1][0]
    np.testing.assert_array_equal(calls[0][0], samples[0:100])
    np.testing.assert_array_equal(calls[1][0], samples[150:350])
    assert calls[0][2]["seed"] is primary_a
    assert calls[0][2]["additional_seeds"] == ()
    assert calls[1][2]["seed"] is primary_b
    assert calls[1][2]["additional_seeds"] == (secondary_b,)
    assert all(call[2]["config"] is settings for call in calls)
    assert all(call[2]["edge"] is StarlinkEdge.UPPER for call in calls)
    assert all(call[2]["maximum_residual_cfo_hz"] == 1_250.0 for call in calls)


def test_piecewise_v4_validates_caller_qualified_segment_bounds() -> None:
    samples = np.ones(300, dtype=np.complex128)
    primary = _seed()

    with pytest.raises(ValueError, match="at least one segment"):
        analyze_piecewise_pilot_pnt_kalman_v4(
            samples,
            RATE,
            segments=(),
            edge=StarlinkEdge.LOWER,
        )
    with pytest.raises(ValueError, match="ordered and nonoverlapping"):
        analyze_piecewise_pilot_pnt_kalman_v4(
            samples,
            RATE,
            segments=(
                PilotPntKalmanV4SegmentSeed(0, 160, primary),
                PilotPntKalmanV4SegmentSeed(150, 250, _additional_seed()),
            ),
            edge=StarlinkEdge.LOWER,
        )
    with pytest.raises(ValueError, match="beyond the sample window"):
        analyze_piecewise_pilot_pnt_kalman_v4(
            samples,
            RATE,
            segments=(PilotPntKalmanV4SegmentSeed(0, 301, primary),),
            edge=StarlinkEdge.LOWER,
        )
