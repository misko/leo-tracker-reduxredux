from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from leo.analysis.standard.native_alternate_tracks import (
    build_standard_native_alternate_cfo_track_bank,
    render_standard_native_alternate_cfo_tracks_png,
)
from leo.contracts.digests import canonical_digest
from leo.contracts.standard_native import StandardNativeSourceV1
from leo.contracts.standard_native_alternate_tracks import (
    NativeAlternateTrackProjectionDispositionV1,
    StandardNativeAlternateCfoTrackBankV4,
)
from leo.contracts.standard_native_stateful import (
    NativePolynomialTrajectoryV1,
    NativeRawTrajectoryBankV1,
    NativeSegmentLocalScienceV1,
)
from leo.contracts.standard_native_stateful_v2 import (
    NativeStatefulSegmentDispositionV2,
    NativeStatefulSegmentV2,
    StandardNativeStatefulPathV2,
)
from leo.contracts.states import StarlinkEdge
from leo.contracts.validity import ContinuitySegmentV1

_RATE = 3_000_000


def _digest(label: str) -> str:
    return canonical_digest({"test": label})


def _continuity_segments(*, gapped: bool) -> tuple[ContinuitySegmentV1, ...]:
    first = ContinuitySegmentV1(
        segment_index=0,
        device_sample_start=0,
        device_sample_stop=_RATE,
        stored_sample_start=0,
        stored_sample_stop=_RATE,
    )
    if not gapped:
        return (first,)
    return (
        first,
        ContinuitySegmentV1(
            segment_index=1,
            device_sample_start=_RATE + _RATE // 10,
            device_sample_stop=2 * _RATE + _RATE // 10,
            stored_sample_start=_RATE,
            stored_sample_stop=2 * _RATE,
            preceding_missing_sample_count=_RATE // 10,
            preceding_boundary_reason="counter_gap",
            preceding_boundary_header_sha256=_digest("boundary"),
        ),
    )


def _source(*, gapped: bool) -> StandardNativeSourceV1:
    segments = _continuity_segments(gapped=gapped)
    missing = _RATE // 10 if gapped else 0
    observed = sum(item.observed_sample_count for item in segments)
    logical = observed + missing
    return StandardNativeSourceV1(
        session_id="session-1",
        stream_id="stream-0",
        radio_id="radio-0",
        receiver_id=0,
        manifest_digest=_digest("manifest"),
        synchronization_inventory_digest=_digest("synchronization"),
        path_input_binding_digest=_digest("path-binding"),
        validity_inventory_digest=_digest("validity"),
        tuned_center_frequency_hz=959_687_500,
        sample_rate_hz=_RATE,
        logical_sample_count=logical,
        observed_sample_count=observed,
        missing_sample_count=missing,
        timing={
            "first_estimate_utc_ns": 1_000_000_000,
            "first_earliest_utc_ns": 999_999_900,
            "first_latest_utc_ns": 1_000_000_100,
            "last_estimate_utc_ns": 4_000_000_000,
            "last_earliest_utc_ns": 3_999_999_900,
            "last_latest_utc_ns": 4_000_000_100,
        },
        continuity_segments=segments,
    )


def _trajectory(label: str = "shared") -> NativePolynomialTrajectoryV1:
    observations = tuple(_digest(f"{label}-observation-{index}") for index in range(4))
    return NativePolynomialTrajectoryV1(
        trajectory_id=_digest(f"{label}-trajectory"),
        method="glrt64",
        polynomial_degree=1,
        reference_time_s=0.1,
        coefficients_hz=(-1_500.0, 42_000.0),
        start_s=0.1,
        end_s=0.8,
        observation_ids=observations,
        point_count=len(observations),
        residual_rms_hz=125.0,
        bic=12.0,
        high_gate=0.0,
        em_iterations=0,
    )


def _local_science(
    label: str,
    tracks: tuple[NativePolynomialTrajectoryV1, ...],
) -> NativeSegmentLocalScienceV1:
    bank = NativeRawTrajectoryBankV1(
        config_digest=_digest(f"{label}-hough-config"),
        trajectories=tracks,
        families=(),
        observation_count=8,
        truncated_trajectory_count=1 if tracks else 0,
    )
    # The builder consumes an already validated upstream contract and only reads
    # this sealed residual-Hough projection.  Constructing the unused downstream
    # stateful fields would obscure that deliberately narrow dependency in this unit test.
    return NativeSegmentLocalScienceV1.model_construct(
        science_digest=_digest(f"{label}-science"),
        pilot_scan_digest=_digest(f"{label}-pilot"),
        raw_trajectory_bank_digest=_digest(f"{label}-raw-bank"),
        residual_hough_bank=bank,
    )


def _stateful(
    *,
    gapped: bool,
    track_segments: frozenset[int] = frozenset(),
    analyzed_segments: frozenset[int] | None = None,
) -> StandardNativeStatefulPathV2:
    source = _source(gapped=gapped)
    analyzed_indexes = (
        frozenset(range(len(source.continuity_segments)))
        if analyzed_segments is None
        else analyzed_segments
    )
    track = _trajectory()
    segments: list[NativeStatefulSegmentV2] = []
    for authority in source.continuity_segments:
        analyzed = authority.segment_index in analyzed_indexes
        local_science = (
            _local_science(
                f"segment-{authority.segment_index}",
                (track,) if authority.segment_index in track_segments else (),
            )
            if analyzed
            else None
        )
        segments.append(
            NativeStatefulSegmentV2.model_construct(
                continuity_segment=authority,
                continuity_segment_index=authority.segment_index,
                global_device_sample_start=authority.device_sample_start,
                global_device_sample_stop=authority.device_sample_stop,
                disposition=(
                    NativeStatefulSegmentDispositionV2.ANALYZED
                    if analyzed
                    else NativeStatefulSegmentDispositionV2.NO_VALID_GLOBAL_PROBE
                ),
                local_science=local_science,
                segment_digest=_digest(f"segment-{authority.segment_index}-stateful"),
            )
        )
    return StandardNativeStatefulPathV2.model_construct(
        source=source,
        starlink_edge=StarlinkEdge.LOWER,
        science_configuration_digest=_digest("science-configuration"),
        stateful_science_status="partial_coverage" if gapped else "complete",
        segments=tuple(segments),
        stateful_path_digest=_digest("stateful-path"),
    )


def _build(stateful: StandardNativeStatefulPathV2) -> StandardNativeAlternateCfoTrackBankV4:
    return build_standard_native_alternate_cfo_track_bank(
        stateful,
        stateful_product_digest=_digest("stateful-product"),
    )


def test_projection_copies_exact_segment_local_tracks_without_refitting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stateful = _stateful(gapped=True, track_segments=frozenset({0, 1}))

    def fail_refit(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("alternate projection must not refit persisted trajectories")

    monkeypatch.setattr(
        "leo.analysis.starlink.trajectory_feedback.fit_residual_hough_pilot_trajectories",
        fail_refit,
    )
    bank = _build(stateful)

    assert bank.source == stateful.source
    assert bank.source_stateful_product_digest == _digest("stateful-product")
    assert bank.source_stateful_path_digest == stateful.stateful_path_digest
    assert bank.projection_status == "partial_coverage"
    assert bank.source_observation_count == 16
    assert bank.detected_track_count == 4
    assert bank.returned_track_count == 2
    assert bank.truncated_track_count == 2
    assert bank.cross_segment_association_permitted is False
    assert tuple(item.projection_disposition for item in bank.segments) == (
        NativeAlternateTrackProjectionDispositionV1.PROJECTED,
        NativeAlternateTrackProjectionDispositionV1.PROJECTED,
    )
    assert bank.segments[0].tracks == bank.segments[1].tracks == (_trajectory(),)
    assert (
        StandardNativeAlternateCfoTrackBankV4.model_validate(bank.model_dump(mode="json")) == bank
    )


def test_lossless_analyzed_empty_bank_is_truthful_no_result() -> None:
    bank = _build(_stateful(gapped=False))

    assert bank.projection_status == "no_result"
    assert bank.source_observation_count == 8
    assert bank.detected_track_count == bank.returned_track_count == 0
    assert bank.segments[0].projection_disposition is (
        NativeAlternateTrackProjectionDispositionV1.NO_CANDIDATE_TRACKS
    )


def test_no_analyzed_segment_is_insufficient_without_fabricated_evidence() -> None:
    bank = _build(
        _stateful(
            gapped=True,
            analyzed_segments=frozenset(),
        )
    )

    assert bank.projection_status == "insufficient_data"
    assert bank.source_observation_count == bank.detected_track_count == 0
    assert bank.returned_track_count == bank.truncated_track_count == 0
    assert all(
        item.projection_disposition
        is NativeAlternateTrackProjectionDispositionV1.NO_STATEFUL_SCIENCE
        for item in bank.segments
    )


def test_projection_rejects_track_outside_its_authoritative_segment() -> None:
    bank = _build(_stateful(gapped=False, track_segments=frozenset({0})))
    assert bank.projection_status == "complete"
    values: dict[str, Any] = bank.model_dump(mode="json")
    segment = values["segments"][0]
    segment["tracks"][0]["end_s"] = 1.01
    segment["segment_projection_digest"] = canonical_digest(
        {key: value for key, value in segment.items() if key != "segment_projection_digest"}
    )
    values["bank_digest"] = canonical_digest(
        {key: value for key, value in values.items() if key != "bank_digest"}
    )

    with pytest.raises(ValidationError, match="escaped segment-local support"):
        StandardNativeAlternateCfoTrackBankV4.model_validate(values)


def test_renderer_consumes_only_the_projection_and_is_deterministic() -> None:
    bank = _build(_stateful(gapped=True, track_segments=frozenset({0, 1})))

    first = render_standard_native_alternate_cfo_tracks_png(bank)
    second = render_standard_native_alternate_cfo_tracks_png(bank)

    assert first.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(first) > 10_000
    assert second == first
