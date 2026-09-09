"""Production persistent-hop metadata port: no IQ retention or capture policy.

PPU owns legacy validation and calls consume only after attesting HOPS/IQ.
Its finite IIO timeout bounds each RPC; the drain budget bounds new attempts,
so worst-case drain time is the budget plus at most one IIO RPC timeout.
"""

from __future__ import annotations

import errno
import math
import secrets
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from leo.contracts.scanner_glrt_frame import DRAIN, ScannerGlrtClassificationV1, inspect_envelope
from leo.contracts.scanner_glrt_request import ScannerGlrtRequestV1, encode_request
from leo.contracts.scanner_glrt_session import ScannerGlrtSessionEvidenceV1
from leo.radio.scanner_glrt_frames import GlrtVisitGeometry, ScannerGlrtFrameReader

if TYPE_CHECKING:
    from pluto_plus.persistent_hop import (
        PersistentHopEvidenceV1,
        PersistentHopRequestV1,
        PersistentHopStatusV1,
    )


@dataclass(frozen=True)
class ScannerGlrtOptions:
    algorithm_sha256: str
    configuration_sha256: str
    drain_budget_seconds: float = 5.0
    mode: str = "unqualified-evidence"

    def __post_init__(self) -> None:
        ScannerGlrtRequestV1(1, self.algorithm_sha256, self.configuration_sha256, b"validate")
        if self.mode not in ("unqualified-evidence", "positive-only-v1"):
            raise ValueError("unsupported GLRT decision profile")
        if (
            isinstance(self.drain_budget_seconds, bool)
            or not isinstance(self.drain_budget_seconds, (int, float))
            or not math.isfinite(self.drain_budget_seconds)
            or not 0 < self.drain_budget_seconds <= 10
        ):
            raise ValueError("GLRT terminal drain budget must be within (0, 10] seconds")


class ScannerGlrtMetadataExtension:
    """One single-use, explicitly opted-in capture session's evidence."""

    def __init__(
        self, options: ScannerGlrtOptions, *, session: int, generation: int | None = None
    ) -> None:
        self.options = options
        self.session = session
        self.generation = (secrets.randbits(64) or 1) if generation is None else generation
        self._geometry: dict[int, GlrtVisitGeometry] = {}
        self._reader = ScannerGlrtFrameReader(
            negotiated=False,
            session=session,
            generation=self.generation,
            algorithm_sha256=options.algorithm_sha256,
            configuration_sha256=options.configuration_sha256,
            maximum_results=2500,
            visit_geometry=self._geometry.get,
        )
        self._request: PersistentHopRequestV1 | None = None
        self._attempted = False
        self._finished = False
        self._error: str | None = "not_negotiated"
        self._expected: int | None = None
        self._delivered_end: int | None = None
        self._results: list[ScannerGlrtClassificationV1] = []

    def negotiate(
        self, request: bytes, attributes: Mapping[str, str], *, drain_supported: bool
    ) -> bytes:
        from pluto_plus.persistent_hop import PersistentHopRequestV1

        from leo.scanner.models import scheduled_low_band_targets

        if self._attempted:
            raise ValueError("GLRT metadata extension is single-use")
        self._attempted = True
        if len(request) != 104 + 288:
            raise ValueError("GLRT requires the existing tandem/HOPR request")
        hop = PersistentHopRequestV1.unpack(request[-288:])
        if hop.session_id != self.session:
            raise ValueError("GLRT request belongs to another session")
        self._request = hop
        required = {
            "iio,buffer-scanner-glrt": "1",
            "iio,buffer-metadata-drain": "1",
            "iio,buffer-scanner-glrt-mode": self.options.mode,
            "iio,buffer-scanner-glrt-algorithm-sha256": self.options.algorithm_sha256,
            "iio,buffer-scanner-glrt-configuration-sha256": self.options.configuration_sha256,
        }
        if not drain_supported or any(attributes.get(k) != v for k, v in required.items()):
            self._error = "unsupported_or_mismatched_classifier"
            return request
        targets = scheduled_low_band_targets(
            bandwidth_hz=hop.sample_rate_hz, lnb_lo_hz=9_750_000_000
        )
        if (
            hop.sample_rate_hz not in (2_500_000, 5_000_000)
            or hop.rf_bandwidth_hz != hop.sample_rate_hz
            or hop.dwell_samples != hop.sample_rate_hz * 120 // 1000
            or not 1 <= hop.dwell_count <= 2500
            or not 0 < hop.capture_span_samples <= hop.sample_rate_hz * 300
            or tuple(p.center_hz for p in hop.profiles) != tuple(t.if_center_hz for t in targets)
        ):
            self._error = "unsupported_classifier_geometry"
            return request
        wrapped = encode_request(
            ScannerGlrtRequestV1(
                self.generation,
                self.options.algorithm_sha256,
                self.options.configuration_sha256,
                request,
            )
        )
        self._reader.negotiated, self._reader.fault = True, None
        self._error = None
        return wrapped

    def unwrap(self, metadata: bytes) -> bytes:
        if not self._reader.negotiated:
            return metadata
        envelope = inspect_envelope(metadata)
        if envelope.flags & DRAIN or not envelope.legacy_metadata:
            raise ValueError("IQ carrier cannot contain a metadata-only drain")
        return envelope.legacy_metadata

    def consume(
        self, metadata: bytes, iq_payload: bytes, *, evidence: PersistentHopEvidenceV1
    ) -> None:
        if not self._reader.negotiated:
            return
        if self._finished or self._request is None or evidence.session_id != self.session:
            raise ValueError("GLRT result outside its source capture session")
        self._delivered_end = evidence.block_end_counter_exclusive
        for event in evidence.events:
            visit = event.dwell_index
            if visit != len(self._geometry) or visit >= self._request.dwell_count:
                raise ValueError("GLRT source inventory is not bounded and contiguous")
            start = event.invalid_end_counter_exclusive
            end = start + self._request.dwell_samples
            if end >= 2**64:
                raise ValueError("GLRT source interval overflows uint64")
            target = event.to_profile_index
            self._geometry[visit] = GlrtVisitGeometry(
                start,
                end,
                self._request.sample_rate_hz,
                target % 4 + 1,
                "lower" if target < 4 else "upper",
                1,
            )
        self._consume_frame(metadata, iq_payload)

    def _consume_frame(self, metadata: bytes, iq_payload: bytes) -> None:
        frame = self._reader.consume(metadata, iq_payload)
        for result in frame.results:
            if self.options.mode == "unqualified-evidence" and result.verdict != "unavailable":
                self.fail("unqualified provider asserted a classification")
                return
            if self.options.mode == "positive-only-v1" and result.verdict == "no_signal":
                self.fail("positive-only provider asserted signal absence")
                return
            if result.search_end > result.search_start and (
                self._delivered_end is None or result.search_end > self._delivered_end
            ):
                self.fail("classifier searched beyond delivered source IQ")
                return
        self._results.extend(frame.results)
        if frame.classification_error:
            self.fail(frame.classification_error)

    def finish(self, status: PersistentHopStatusV1, drain: Callable[[int], bytes]) -> None:
        from pluto_plus.persistent_hop import PersistentHopSessionState

        if self._finished:
            raise ValueError("GLRT terminal reconciliation is single-use")
        self._finished = True
        if (
            self._request is None
            or status.session_id != self.session
            or status.state
            not in (PersistentHopSessionState.COMPLETED, PersistentHopSessionState.CANCELLED)
            or not 0 <= status.visits_started <= self._request.dwell_count
            or self._reader.negotiated
            and status.visits_started != len(self._geometry)
        ):
            self.fail("terminal source inventory mismatch")
            return
        self._expected = status.visits_started
        if not self._reader.negotiated:
            return
        deadline = time.monotonic() + self.options.drain_budget_seconds
        for _attempt in range(1024):
            if time.monotonic() >= deadline:
                self.fail("terminal_drain_timeout")
                return
            try:
                packet = drain(65536)
            except OSError as error:
                if error.errno in (errno.EAGAIN, errno.EBUSY):
                    time.sleep(min(0.005, max(0.0, deadline - time.monotonic())))
                    continue
                self.fail(f"terminal drain failed: {error}")
                return
            self._consume_frame(packet, b"")
            if self._reader.final:
                if self._reader.limit != self._expected or (
                    len(self._results) + self._reader.dropped != self._expected
                ):
                    self.fail("terminal_result_inventory_incomplete")
                return
        self.fail("terminal_drain_attempt_limit")

    def fail(self, reason: str) -> None:
        if self._error is None or self._error == "not_negotiated":
            self._error = str(reason)[:2048] or "classifier_failed"
        if self._reader.negotiated:
            self._reader.fault = self._error

    def snapshot(self) -> ScannerGlrtSessionEvidenceV1:
        results = tuple(self._results)
        complete = (
            self._reader.negotiated
            and self._expected is not None
            and self._reader.final
            and self._error is None
            and not self._reader.dropped
            and len(results) == self._expected == self._reader.limit
            and {r.visit for r in results} == set(range(self._expected))
            and tuple(r.sequence for r in results) == tuple(range(len(results)))
        )
        return ScannerGlrtSessionEvidenceV1(
            session=self.session,
            generation=self.generation,
            algorithm_sha256=self.options.algorithm_sha256,
            configuration_sha256=self.options.configuration_sha256,
            negotiated=self._reader.negotiated,
            mode=self.options.mode if self._reader.negotiated else None,
            source_terminal_attested=self._expected is not None,
            final_received=self._reader.final,
            expected_results=self._expected,
            dropped_results=self._reader.dropped,
            result_sequence_limit=self._reader.limit,
            results=results,
            delivery_complete=complete,
            classification_complete=(
                complete and bool(results) and all(r.verdict != "unavailable" for r in results)
            ),
            error=self._error,
        )
