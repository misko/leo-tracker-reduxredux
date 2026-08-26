"""Digest-pinned odd-Qin response adapter for the final holdout.

Only the narrow source port in this module may read a guarded target frame.  The
numerical estimator demodulates zero-based odd Qin symbols only; the request and
result contracts contain no target-even statistic or training decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Protocol

import numpy as np

from leo.analysis.qam import PilotFrameCfoConfig, estimate_edge_pilot_frame_complex_odd
from leo.analysis.research.doppler_holdout_pre_response import (
    ForecastTargetKeyV1,
    OddQinResponseRequestV1,
    OddQinTargetAuthorityV1,
)
from leo.analysis.research.doppler_holdout_response_v2 import OddQinResponseMeasurementV2
from leo.analysis.starlink import NumericalStatus
from leo.contracts.digests import Sha256Digest


class OddQinFrameUnavailable(RuntimeError):
    """The exact frozen guarded frame could not be supplied."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class AuthorizedOddChunk:
    session_id: str
    stream_id: str
    relative_path: str
    sample_start: int
    sample_count: int
    compressed_sha256: Sha256Digest


@dataclass(frozen=True, slots=True)
class OddChunkReadReceipt:
    relative_path: str
    compressed_sha256: Sha256Digest


@dataclass(frozen=True, slots=True)
class OddQinFrameReadRequest:
    authority: OddQinTargetAuthorityV1
    sample_rate_hz: int
    recording_manifest_sha256: Sha256Digest
    chunks: tuple[AuthorizedOddChunk, ...]


@dataclass(frozen=True, slots=True)
class GuardedOddQinFrame:
    target: ForecastTargetKeyV1
    samples: np.ndarray
    sample_rate_hz: int
    recording_manifest_sha256: Sha256Digest
    chunks: tuple[OddChunkReadReceipt, ...]


class OddQinGuardedFrameSource(Protocol):
    """Storage-owned port that returns one frame plus one-sample guards."""

    def read_guarded_odd_qin_frame(
        self,
        request: OddQinFrameReadRequest,
    ) -> GuardedOddQinFrame:
        """Read the exact source-bound target frame."""


class DigestPinnedOddQinAdapter:
    """Concrete response port sealed to one prediction ledger and authority set."""

    def __init__(
        self,
        *,
        prediction_ledger_digest: Sha256Digest,
        authorities: tuple[OddQinTargetAuthorityV1, ...],
        recording_manifest_sha256_by_session: dict[str, Sha256Digest],
        sample_rate_hz_by_session: dict[str, int],
        authorized_chunks: tuple[AuthorizedOddChunk, ...],
        source: OddQinGuardedFrameSource,
        minimum_exact_coherence: float = 0.02,
        minimum_coherence_margin: float = 0.0,
    ) -> None:
        authority_by_key = {item.target.identity(): item for item in authorities}
        if not authority_by_key or len(authority_by_key) != len(authorities):
            raise ValueError("odd adapter authorities must be nonempty and unique")
        self._prediction_digest = prediction_ledger_digest
        self._authorities = authority_by_key
        sessions = {item.target.session_id for item in authorities}
        if (
            set(recording_manifest_sha256_by_session) != sessions
            or set(sample_rate_hz_by_session) != sessions
        ):
            raise ValueError("odd adapter manifest/sample-rate authorities disagree")
        if any(value <= 0 for value in sample_rate_hz_by_session.values()):
            raise ValueError("odd adapter sample rate must be positive")
        PilotFrameCfoConfig(
            minimum_exact_coherence=minimum_exact_coherence,
            minimum_coherence_margin=minimum_coherence_margin,
        )
        chunk_keys = {
            (item.session_id, item.stream_id, item.relative_path) for item in authorized_chunks
        }
        if not authorized_chunks or len(chunk_keys) != len(authorized_chunks):
            raise ValueError("authorized odd chunk inventory is empty or duplicated")
        if {item.session_id for item in authorized_chunks} != sessions:
            raise ValueError("authorized odd chunks do not cover exactly the frozen sessions")
        by_stream: dict[tuple[str, str], list[AuthorizedOddChunk]] = {}
        for item in authorized_chunks:
            path = PurePosixPath(item.relative_path)
            if (
                path.is_absolute()
                or ".." in path.parts
                or item.sample_start < 0
                or item.sample_count <= 0
            ):
                raise ValueError("authorized odd chunk geometry or path is invalid")
            by_stream.setdefault((item.session_id, item.stream_id), []).append(item)
        for items in by_stream.values():
            ordered = sorted(items, key=lambda item: item.sample_start)
            if any(
                left.sample_start + left.sample_count > right.sample_start
                for left, right in zip(ordered, ordered[1:], strict=False)
            ):
                raise ValueError("authorized odd chunks overlap")
        self._recording_manifest_sha256 = dict(recording_manifest_sha256_by_session)
        self._sample_rate_hz = dict(sample_rate_hz_by_session)
        self._chunks = authorized_chunks
        self._source = source
        self._minimum_exact_coherence = minimum_exact_coherence
        self._minimum_coherence_margin = minimum_coherence_margin
        used_chunks: set[AuthorizedOddChunk] = set()
        for authority in authorities:
            used_chunks.update(self._expected_chunks(authority))
        if used_chunks != set(authorized_chunks):
            raise ValueError("authorized odd chunk inventory contains an unused chunk")

    def measure_odd_qin(
        self,
        request: OddQinResponseRequestV1,
    ) -> OddQinResponseMeasurementV2:
        """Verify the frozen request and measure only its odd Qin fold."""

        if request.prediction_ledger_digest != self._prediction_digest:
            raise ValueError("odd request uses another prediction ledger")
        expected = self._authorities.get(request.authority.target.identity())
        if expected is None or request.authority != expected:
            raise ValueError("odd request authority is absent or differs from the freeze")
        session_id = request.authority.target.session_id
        expected_rate = self._sample_rate_hz[session_id]
        expected_manifest = self._recording_manifest_sha256[session_id]
        expected_chunks = self._expected_chunks(request.authority)
        try:
            guarded = self._source.read_guarded_odd_qin_frame(
                OddQinFrameReadRequest(
                    authority=request.authority,
                    sample_rate_hz=expected_rate,
                    recording_manifest_sha256=expected_manifest,
                    chunks=expected_chunks,
                )
            )
        except OddQinFrameUnavailable as error:
            return OddQinResponseMeasurementV2(
                prediction_ledger_digest=self._prediction_digest,
                target=request.authority.target,
                status="missing",
                missing_reason=error.reason,
                accuracy_disposition="missing",
            )
        if guarded.target != request.authority.target:
            raise ValueError("odd frame source returned another target")
        if guarded.sample_rate_hz != expected_rate:
            raise ValueError("odd frame sample rate differs from frozen authority")
        if guarded.recording_manifest_sha256 != expected_manifest:
            raise ValueError("odd frame recording manifest differs from frozen authority")
        expected_receipts = tuple(
            OddChunkReadReceipt(
                relative_path=item.relative_path,
                compressed_sha256=item.compressed_sha256,
            )
            for item in expected_chunks
        )
        if guarded.chunks != expected_receipts:
            raise ValueError("odd source chunk receipt differs from frozen inventory")
        observation = estimate_edge_pilot_frame_complex_odd(
            guarded.samples,
            guarded.sample_rate_hz,
            frame_start_sample=request.authority.target.frame_start_sample,
            acquisition_absolute_cfo_hz=request.authority.acquisition_absolute_cfo_hz,
            edge=request.authority.edge,
            config=PilotFrameCfoConfig(
                residual_half_width_hz=request.authority.residual_half_width_hz,
                minimum_exact_coherence=self._minimum_exact_coherence,
                minimum_coherence_margin=self._minimum_coherence_margin,
            ),
        )
        if observation.status is not NumericalStatus.COMPLETE or observation.odd is None:
            return OddQinResponseMeasurementV2(
                prediction_ledger_digest=self._prediction_digest,
                target=request.authority.target,
                status="missing",
                missing_reason="odd_estimator_no_result",
                accuracy_disposition="missing",
            )
        odd = observation.odd
        common = {
            "prediction_ledger_digest": self._prediction_digest,
            "target": request.authority.target,
            "odd_absolute_cfo_hz": odd.absolute_cfo_hz,
            "odd_frequency_uncertainty_hz": odd.frequency_uncertainty_hz,
            "odd_exact_coherence": odd.exact_coherence,
            "odd_rolled_control_coherence": odd.control_coherence,
            "odd_coherence_margin": odd.coherence_margin,
            "odd_phase_residual_rms_rad": odd.phase_residual_rms_rad,
            "odd_search_boundary": odd.search_boundary,
        }
        if odd.search_boundary:
            return OddQinResponseMeasurementV2.model_validate(
                {**common, "status": "boundary", "accuracy_disposition": "excluded_boundary"}
            )
        support_reasons: list[str] = []
        if odd.exact_coherence < self._minimum_exact_coherence:
            support_reasons.append("odd_exact_coherence_below_minimum")
        if odd.coherence_margin < self._minimum_coherence_margin:
            support_reasons.append("odd_coherence_margin_below_minimum")
        if support_reasons:
            return OddQinResponseMeasurementV2.model_validate(
                {
                    **common,
                    "status": "no_support",
                    "support_reasons": tuple(support_reasons),
                    "accuracy_disposition": "excluded_no_support",
                }
            )
        return OddQinResponseMeasurementV2.model_validate(
            {**common, "status": "finite", "accuracy_disposition": "eligible"}
        )

    def _expected_chunks(
        self,
        authority: OddQinTargetAuthorityV1,
    ) -> tuple[AuthorizedOddChunk, ...]:
        session_id = authority.target.session_id
        if session_id not in self._sample_rate_hz:
            raise ValueError("target session is outside odd authority")
        frame_content = round(302 * self._sample_rate_hz[session_id] * 4.4e-6)
        read_start = authority.target.frame_start_sample - 1
        read_stop = authority.target.frame_start_sample + frame_content + 1
        expected = tuple(
            item
            for item in self._chunks
            if item.session_id == session_id
            and item.stream_id == authority.stream_id
            and item.sample_start < read_stop
            and item.sample_start + item.sample_count > read_start
        )
        expected = tuple(sorted(expected, key=lambda item: item.sample_start))
        if not expected:
            raise ValueError("target is outside the authorized odd chunk inventory")
        cursor = read_start
        for chunk in expected:
            if chunk.sample_start > cursor:
                raise ValueError("authorized odd chunks do not cover the guarded frame")
            cursor = max(cursor, chunk.sample_start + chunk.sample_count)
        if cursor < read_stop:
            raise ValueError("authorized odd chunks do not cover the guarded frame")
        return expected
