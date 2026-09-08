"""Host-side classification binding without IQ buffering or capture policy changes.

The concrete LIBIIO adapter must negotiate the envelope and register legacy
hop evidence before consume(). Classification faults disable classification
for this session while leaving structurally recoverable IQ/metadata intact.
This module does not yet change or call the installed LIBIIO runtime.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from leo.contracts.scanner_glrt_frame import (
    DETECTOR_FAILED,
    DRAIN,
    FINAL,
    ScannerGlrtClassificationV1,
    decode_frame,
    inspect_envelope,
)


@dataclass(frozen=True, slots=True)
class GlrtVisitGeometry:
    valid_start: int
    valid_end: int
    rate_hz: int
    channel: int
    edge: str
    rx: int


@dataclass(frozen=True, slots=True)
class ClassifiedScannerFrame:
    legacy_metadata: bytes
    iq: bytes | memoryview
    results: tuple[ScannerGlrtClassificationV1, ...]
    final: bool
    classification_error: str | None


class ScannerGlrtFrameReader:
    def __init__(
        self,
        *,
        negotiated: bool,
        session: int,
        generation: int,
        algorithm_sha256: str,
        configuration_sha256: str,
        maximum_results: int,
        visit_geometry: Callable[[int], GlrtVisitGeometry | None],
    ):
        if (
            type(negotiated) is not bool
            or type(maximum_results) is not int
            or not 1 <= maximum_results <= 2500
            or type(session) is not int
            or not 0 < session < 2**64
            or type(generation) is not int
            or not 0 < generation < 2**64
        ):
            raise ValueError("bounded scanner session identity required")
        for digest in (algorithm_sha256, configuration_sha256):
            if (
                not isinstance(digest, str)
                or len(digest) != 64
                or digest == "0" * 64
                or any(c not in "0123456789abcdef" for c in digest)
            ):
                raise ValueError("classifier artifact identities must be SHA-256 digests")
        self.negotiated = negotiated
        self.session, self.generation = session, generation
        self.algorithm_sha256, self.configuration_sha256 = algorithm_sha256, configuration_sha256
        self.maximum_results, self.visit_geometry = maximum_results, visit_geometry
        self.next_frame, self.next_result, self.limit, self.dropped, self.holes = 0, 0, 0, 0, 0
        self.draining, self.final = False, False
        self.fault: str | None = None if negotiated else "unsupported"
        self.visits: set[int] = set()
        self.counts = {"starlink": 0, "no_signal": 0, "unavailable": 0}

    def consume(self, metadata: bytes, iq: bytes | memoryview) -> ClassifiedScannerFrame:
        if not self.negotiated:
            return ClassifiedScannerFrame(metadata, iq, (), False, "unsupported")
        # Framing failures cannot be guessed. GLRT semantic failures below can
        # be isolated because the legacy slice boundaries are independently known.
        envelope = inspect_envelope(metadata)
        drain, final = bool(envelope.flags & DRAIN), bool(envelope.flags & FINAL)
        if (
            envelope.flags > 7
            or final
            and not drain
            or drain != (len(iq) == 0)
            or drain != (len(envelope.legacy_metadata) == 0)
            or self.final
            or self.draining
            and not drain
        ):
            raise ValueError("classification envelope/IQ framing is inconsistent")
        results = ()
        if self.fault is None:
            try:
                frame = decode_frame(metadata)
                if (
                    frame.session != self.session
                    or frame.generation != self.generation
                    or frame.algorithm_sha256 != self.algorithm_sha256
                    or frame.configuration_sha256 != self.configuration_sha256
                    or frame.frame_sequence != self.next_frame
                    or not self.limit <= frame.result_sequence_limit <= self.maximum_results
                    or frame.dropped_results < self.dropped
                ):
                    raise ValueError("classification session, sequence, or provenance mismatch")
                next_result, holes = self.next_result, self.holes
                visits = set(self.visits)
                counts = dict(self.counts)
                for result in frame.results:
                    if result.sequence < next_result or result.visit in visits:
                        raise ValueError("duplicate or reversed dwell classification")
                    geometry = self.visit_geometry(result.visit)
                    if geometry is None or geometry != GlrtVisitGeometry(
                        result.valid_start,
                        result.valid_end,
                        result.rate_hz,
                        result.channel,
                        result.edge,
                        result.rx,
                    ):
                        raise ValueError("classification is not bound to an attested dwell")
                    holes += result.sequence - next_result
                    next_result = result.sequence + 1
                    visits.add(result.visit)
                    counts[result.verdict] += 1
                if final:
                    holes += frame.result_sequence_limit - next_result
                    next_result = frame.result_sequence_limit
                if holes > frame.dropped_results or final and holes != frame.dropped_results:
                    raise ValueError("classification sequence holes lack loss accounting")
                if len(visits) > self.maximum_results:
                    raise ValueError("classification inventory exceeds session bound")
                self.next_result, self.holes, self.visits, self.counts = (
                    next_result,
                    holes,
                    visits,
                    counts,
                )
                self.limit, self.dropped = frame.result_sequence_limit, frame.dropped_results
                self.next_frame += 1
                results = frame.results
                if frame.flags & DETECTOR_FAILED:
                    self.fault = "worker_failed"
            except (ValueError, LookupError) as exc:
                self.fault = str(exc)
        self.draining, self.final = drain, final
        return ClassifiedScannerFrame(envelope.legacy_metadata, iq, results, final, self.fault)

    def summary(self, expected_results: int) -> dict:
        """Expected count comes from the qualified capture receipt, not GLRT."""
        if type(expected_results) is not int or not 0 <= expected_results <= self.maximum_results:
            raise ValueError("invalid expected classification count")
        complete = (
            self.negotiated
            and self.final
            and self.fault is None
            and self.limit == expected_results
            and len(self.visits) + self.dropped == expected_results
            and not self.dropped
            and not self.counts["unavailable"]
        )
        return {
            "complete": complete,
            "expected": expected_results,
            "received": len(self.visits),
            "dropped": self.dropped,
            **self.counts,
            "error": self.fault,
        }
