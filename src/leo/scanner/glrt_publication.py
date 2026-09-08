"""Bind optional classifier evidence to public, independent capture receipts."""

from typing import Protocol

from leo.contracts.scanner_glrt_publication import ScannerGlrtPublicationV1
from leo.contracts.scanner_glrt_session import ScannerGlrtSessionEvidenceV1
from leo.scanner.persistent_hop import (
    PersistentHopSessionReceiptV1,
    persistent_hop_wire_session_id,
)


class ScannerGlrtEvidenceSource(Protocol):
    """Optional radio capability; read only after capture and close complete."""

    @property
    def classification_evidence(self) -> ScannerGlrtSessionEvidenceV1 | None: ...

    @property
    def classification_error(self) -> str | None: ...


class ScannerGlrtPublicationReader(Protocol):
    def detail(self, session_id: str) -> ScannerGlrtPublicationV1 | None: ...


def validate_glrt_capture_binding(
    publication: ScannerGlrtPublicationV1,
    receipt: PersistentHopSessionReceiptV1,
    *,
    input_manifest_sha256: str,
) -> None:
    """Reject cross-session, stale-source and out-of-source classifications.

    This validates linkage only. It neither relaxes the session's classification
    policy nor promotes an unqualified candidate to a Starlink verdict.
    """
    if (
        publication.session_id != receipt.session_id
        or publication.input_manifest_sha256 != input_manifest_sha256
    ):
        raise ValueError("GLRT publication is bound to a different capture")
    evidence = publication.evidence
    if evidence is None:
        return
    if evidence.session != persistent_hop_wire_session_id(receipt.session_id):
        raise ValueError("GLRT wire session disagrees with capture identity")
    if evidence.source_terminal_attested and evidence.expected_results != len(receipt.visits):
        raise ValueError("GLRT terminal inventory disagrees with capture receipt")
    for result in evidence.results:
        if result.visit >= len(receipt.visits):
            raise ValueError("GLRT result names a visit absent from the capture")
        visit = receipt.visits[result.visit]
        if (
            result.rate_hz != receipt.plan.sample_rate_hz
            or result.rx not in receipt.plan.receiver_ids
            or result.channel != visit.target.channel
            or result.edge != visit.target.edge
            or result.valid_start != visit.valid_device_sample_counter
            or result.valid_end != visit.valid_device_sample_counter + visit.valid_sample_count
        ):
            raise ValueError("GLRT result interval or geometry disagrees with capture receipt")
