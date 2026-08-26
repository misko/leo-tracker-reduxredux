from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from leo.analysis.research.doppler_holdout_odd_adapter import (
    AuthorizedOddChunk,
    DigestPinnedOddQinAdapter,
    GuardedOddQinFrame,
    OddChunkReadReceipt,
    OddQinFrameReadRequest,
    OddQinFrameUnavailable,
    preflight_exact_authorized_odd_chunks,
    resolve_authorized_odd_chunks_by_target,
)
from leo.analysis.research.doppler_holdout_pre_response import (
    ForecastTargetKeyV1,
    OddQinResponseRequestV1,
    OddQinTargetAuthorityV1,
)
from leo.analysis.starlink import qin_edge_pilot_frame
from leo.analysis.starlink.templates import OFDM_SYMBOL_DURATION_S, StarlinkEdge

DIGEST = "sha256:" + "1" * 64
OTHER_DIGEST = "sha256:" + "2" * 64
RATE_HZ = 2_500_000


def _target() -> ForecastTargetKeyV1:
    return ForecastTargetKeyV1(
        session_id="capture-a",
        episode_id=DIGEST,
        target_mask_digest=OTHER_DIGEST,
        frame_start_sample=1_000_000,
        reference_sample=1_001_667.0,
        continuity_segment_id=0,
    )


def _authority() -> OddQinTargetAuthorityV1:
    return OddQinTargetAuthorityV1(
        target=_target(),
        scope_key=DIGEST,
        stream_id="stream-0",
        radio_id="radio-a",
        receiver_id=0,
        edge="lower",
        source_id=DIGEST,
        branch_id=OTHER_DIGEST,
        trajectory_id=DIGEST,
        acquisition_absolute_cfo_hz=100_000.0,
    )


def _samples(cfo_hz: float = 100_500.0) -> np.ndarray:
    frame_content = round(302 * RATE_HZ * OFDM_SYMBOL_DURATION_S)
    template = np.asarray(qin_edge_pilot_frame(RATE_HZ, StarlinkEdge.LOWER))[:frame_content]
    absolute = _target().frame_start_sample + np.arange(frame_content)
    values = np.zeros(frame_content + 2, dtype=np.complex128)
    values[1:-1] = template * np.exp(2j * np.pi * cfo_hz * absolute / RATE_HZ)
    return values


def _chunk() -> AuthorizedOddChunk:
    return AuthorizedOddChunk(
        session_id="capture-a",
        stream_id="stream-0",
        relative_path="radio-a/iq-000000.ci16.zst",
        sample_start=0,
        sample_count=2_000_000,
        compressed_sha256=OTHER_DIGEST,
    )


def _guarded(
    authority: OddQinTargetAuthorityV1, samples: np.ndarray | None = None
) -> GuardedOddQinFrame:
    return GuardedOddQinFrame(
        target=authority.target,
        samples=_samples() if samples is None else samples,
        sample_rate_hz=RATE_HZ,
        recording_manifest_sha256=DIGEST,
        chunks=(
            OddChunkReadReceipt(
                relative_path=_chunk().relative_path,
                compressed_sha256=_chunk().compressed_sha256,
            ),
        ),
    )


def _adapter(
    source: object,
    *,
    authority: OddQinTargetAuthorityV1 | None = None,
    **kwargs: float,
) -> DigestPinnedOddQinAdapter:
    selected_authority = _authority() if authority is None else authority
    return DigestPinnedOddQinAdapter(
        prediction_ledger_digest=DIGEST,
        authorities=(selected_authority,),
        recording_manifest_sha256_by_session={"capture-a": DIGEST},
        sample_rate_hz_by_session={"capture-a": RATE_HZ},
        authorized_chunks=(_chunk(),),
        source=source,  # type: ignore[arg-type]
        **kwargs,
    )


def test_adapter_request_and_result_have_no_target_even_statistic() -> None:
    authority = _authority()

    class SpySource:
        def read_guarded_odd_qin_frame(self, request: OddQinFrameReadRequest) -> GuardedOddQinFrame:
            observed = request.authority
            assert "even_absolute_cfo" not in repr(observed.model_dump(mode="json")).lower()
            return _guarded(observed)

    adapter = _adapter(SpySource())
    response = adapter.measure_odd_qin(
        OddQinResponseRequestV1(prediction_ledger_digest=DIGEST, authority=authority)
    )

    assert response.status == "finite"
    assert response.odd_absolute_cfo_hz == pytest.approx(100_500.0, abs=1.0)
    assert "even" not in repr(response.model_dump(mode="json")).lower()


def test_adapter_preserves_missing_without_substitution() -> None:
    authority = _authority()

    class MissingSource:
        def read_guarded_odd_qin_frame(self, request: OddQinFrameReadRequest) -> GuardedOddQinFrame:
            raise OddQinFrameUnavailable("authorized_chunk_unavailable")

    adapter = _adapter(MissingSource())
    response = adapter.measure_odd_qin(
        OddQinResponseRequestV1(prediction_ledger_digest=DIGEST, authority=authority)
    )

    assert response.status == "missing"
    assert response.missing_reason == "authorized_chunk_unavailable"
    assert response.odd_absolute_cfo_hz is None


def test_adapter_rejects_any_authority_drift_before_source_access() -> None:
    authority = _authority()

    class ForbiddenSource:
        def read_guarded_odd_qin_frame(self, request: OddQinFrameReadRequest) -> GuardedOddQinFrame:
            raise AssertionError("source must not be called")

    adapter = _adapter(ForbiddenSource())
    changed = authority.model_copy(update={"acquisition_absolute_cfo_hz": 999.0})

    with pytest.raises(ValueError, match="authority"):
        adapter.measure_odd_qin(
            OddQinResponseRequestV1(prediction_ledger_digest=DIGEST, authority=changed)
        )


def test_adapter_retains_numeric_specificity_for_no_support_and_boundary() -> None:
    authority = _authority()

    class NoSupportSource:
        def read_guarded_odd_qin_frame(self, request: OddQinFrameReadRequest) -> GuardedOddQinFrame:
            return _guarded(request.authority)

    no_support = _adapter(NoSupportSource(), minimum_coherence_margin=1.0).measure_odd_qin(
        OddQinResponseRequestV1(prediction_ledger_digest=DIGEST, authority=authority)
    )
    assert no_support.status == "no_support"
    assert no_support.odd_exact_coherence is not None
    assert no_support.odd_rolled_control_coherence is not None
    assert no_support.odd_search_boundary is False

    boundary_authority = authority.model_copy(update={"residual_half_width_hz": 100.0})

    class BoundarySource:
        def read_guarded_odd_qin_frame(self, request: OddQinFrameReadRequest) -> GuardedOddQinFrame:
            return _guarded(request.authority)

    boundary = _adapter(BoundarySource(), authority=boundary_authority).measure_odd_qin(
        OddQinResponseRequestV1(prediction_ledger_digest=DIGEST, authority=boundary_authority)
    )
    assert boundary.status == "boundary"
    assert boundary.accuracy_disposition == "excluded_boundary"
    assert boundary.odd_exact_coherence is not None


def test_adapter_rejects_sample_rate_manifest_and_chunk_receipt_drift() -> None:
    authority = _authority()

    class DriftSource:
        def __init__(self, field: str) -> None:
            self.field = field

        def read_guarded_odd_qin_frame(self, request: OddQinFrameReadRequest) -> GuardedOddQinFrame:
            baseline = _guarded(request.authority)
            if self.field == "rate":
                return GuardedOddQinFrame(
                    target=baseline.target,
                    samples=baseline.samples,
                    sample_rate_hz=RATE_HZ + 1,
                    recording_manifest_sha256=baseline.recording_manifest_sha256,
                    chunks=baseline.chunks,
                )
            if self.field == "manifest":
                return GuardedOddQinFrame(
                    target=baseline.target,
                    samples=baseline.samples,
                    sample_rate_hz=baseline.sample_rate_hz,
                    recording_manifest_sha256=OTHER_DIGEST,
                    chunks=baseline.chunks,
                )
            return GuardedOddQinFrame(
                target=baseline.target,
                samples=baseline.samples,
                sample_rate_hz=baseline.sample_rate_hz,
                recording_manifest_sha256=baseline.recording_manifest_sha256,
                chunks=(
                    OddChunkReadReceipt(
                        relative_path="substituted.ci16.zst",
                        compressed_sha256=OTHER_DIGEST,
                    ),
                ),
            )

    for field in ("rate", "manifest", "chunk"):
        with pytest.raises(ValueError, match="sample rate|manifest|chunk"):
            _adapter(DriftSource(field)).measure_odd_qin(
                OddQinResponseRequestV1(
                    prediction_ledger_digest=DIGEST,
                    authority=authority,
                )
            )


def test_chunk_gap_overlap_wrong_stream_and_unused_inventory_fail_before_source() -> None:
    authority = _authority()

    class ForbiddenSource:
        def read_guarded_odd_qin_frame(self, request: OddQinFrameReadRequest) -> GuardedOddQinFrame:
            raise AssertionError("source must not be called")

    base = _chunk()
    bad_inventories = (
        (replace(base, sample_count=authority.target.frame_start_sample - 2),),
        (
            base,
            replace(
                base,
                relative_path="radio-a/overlap.ci16.zst",
                sample_start=500_000,
            ),
        ),
        (replace(base, stream_id="stream-1"),),
        (
            base,
            replace(
                base,
                relative_path="radio-a/unused.ci16.zst",
                sample_start=3_000_000,
            ),
        ),
    )
    for chunks in bad_inventories:
        with pytest.raises(ValueError, match="cover|overlap|outside|unused"):
            DigestPinnedOddQinAdapter(
                prediction_ledger_digest=DIGEST,
                authorities=(authority,),
                recording_manifest_sha256_by_session={"capture-a": DIGEST},
                sample_rate_hz_by_session={"capture-a": RATE_HZ},
                authorized_chunks=chunks,
                source=ForbiddenSource(),
            )


def test_pure_chunk_resolver_uses_exact_half_open_one_sample_guards() -> None:
    frame_start = 10_000
    frame_content = round(302 * RATE_HZ * OFDM_SYMBOL_DURATION_S)
    read_start = frame_start - 1
    read_stop = frame_start + frame_content + 1
    split = read_start + 101
    target = _target().model_copy(
        update={
            "frame_start_sample": frame_start,
            "reference_sample": float(frame_start + frame_content // 2),
        }
    )
    authority = _authority().model_copy(update={"target": target})
    before = replace(
        _chunk(),
        relative_path="radio-a/before.ci16.zst",
        sample_start=0,
        sample_count=read_start,
    )
    left = replace(
        _chunk(),
        relative_path="radio-a/left.ci16.zst",
        sample_start=read_start,
        sample_count=split - read_start,
    )
    right = replace(
        _chunk(),
        relative_path="radio-a/right.ci16.zst",
        sample_start=split,
        sample_count=read_stop - split,
    )
    after = replace(
        _chunk(),
        relative_path="radio-a/after.ci16.zst",
        sample_start=read_stop,
        sample_count=100,
    )

    resolved = resolve_authorized_odd_chunks_by_target(
        authorities=(authority,),
        sample_rate_hz_by_session={"capture-a": RATE_HZ},
        authorized_chunks=(after, right, before, left),
    )

    assert read_stop - read_start == frame_content + 2 == 3_324
    assert resolved == ((left, right),)
    assert before.sample_start + before.sample_count == read_start
    assert after.sample_start == read_stop


def test_pure_chunk_preflight_rejects_unused_and_each_required_removal() -> None:
    frame_start = 10_000
    frame_content = round(302 * RATE_HZ * OFDM_SYMBOL_DURATION_S)
    read_start = frame_start - 1
    read_stop = frame_start + frame_content + 1
    split = read_start + 101
    target = _target().model_copy(
        update={
            "frame_start_sample": frame_start,
            "reference_sample": float(frame_start + frame_content // 2),
        }
    )
    authority = _authority().model_copy(update={"target": target})
    required = (
        replace(
            _chunk(),
            relative_path="radio-a/left.ci16.zst",
            sample_start=read_start,
            sample_count=split - read_start,
        ),
        replace(
            _chunk(),
            relative_path="radio-a/right.ci16.zst",
            sample_start=split,
            sample_count=read_stop - split,
        ),
    )
    unused = replace(
        _chunk(),
        relative_path="radio-a/unused.ci16.zst",
        sample_start=read_stop,
        sample_count=100,
    )

    assert preflight_exact_authorized_odd_chunks(
        authorities=(authority,),
        sample_rate_hz_by_session={"capture-a": RATE_HZ},
        authorized_chunks=required,
    ) == (required,)
    with pytest.raises(ValueError, match="unused chunk"):
        preflight_exact_authorized_odd_chunks(
            authorities=(authority,),
            sample_rate_hz_by_session={"capture-a": RATE_HZ},
            authorized_chunks=required + (unused,),
        )
    for removed in required:
        with pytest.raises(ValueError, match="cover"):
            preflight_exact_authorized_odd_chunks(
                authorities=(authority,),
                sample_rate_hz_by_session={"capture-a": RATE_HZ},
                authorized_chunks=tuple(chunk for chunk in required if chunk != removed),
            )


def test_adapter_retains_unused_chunk_guard_without_source_access() -> None:
    authority = _authority()

    class ForbiddenSource:
        calls = 0

        def read_guarded_odd_qin_frame(self, request: OddQinFrameReadRequest) -> GuardedOddQinFrame:
            self.calls += 1
            raise AssertionError("source must not be called")

    source = ForbiddenSource()
    unused = replace(
        _chunk(),
        relative_path="radio-a/unused.ci16.zst",
        sample_start=3_000_000,
    )

    with pytest.raises(ValueError, match="unused chunk"):
        DigestPinnedOddQinAdapter(
            prediction_ledger_digest=DIGEST,
            authorities=(authority,),
            recording_manifest_sha256_by_session={"capture-a": DIGEST},
            sample_rate_hz_by_session={"capture-a": RATE_HZ},
            authorized_chunks=(_chunk(), unused),
            source=source,
        )

    assert source.calls == 0
