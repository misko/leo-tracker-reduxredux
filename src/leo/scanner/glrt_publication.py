"""Bind optional classifier evidence to public, independent capture receipts."""

from typing import Protocol

from leo.contracts.scanner_glrt_publication import ScannerGlrtPublicationV1
from leo.contracts.scanner_glrt_session import ScannerGlrtSessionEvidenceV1
from leo.scanner.adaptive_hop import AdaptiveHopReceiptV1
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

    This validates linkage and the admitted application profile. It never
    promotes unqualified evidence. Published major-v1 layouts stay unchanged.
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
        if evidence.mode == "positive-only-v1" and result.verdict == "no_signal":
            raise ValueError("positive-only GLRT profile cannot assert signal absence")
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


def validate_glrt_adaptive_binding(
    publication: ScannerGlrtPublicationV1,
    receipt: AdaptiveHopReceiptV1,
    *,
    input_manifest_sha256: str,
) -> None:
    """Bind V2 scheduling evidence without weakening fixed-hop validation.

    The detector inventory covers every *started* event, including a cancelled
    final dwell that was not retained as complete IQ. Its nominal valid interval
    is not proof of capture: any actual search must end within delivered source
    IQ and before RF stopped. Consumers must show retained-IQ status separately.
    """
    publication = ScannerGlrtPublicationV1.model_validate(publication.model_dump())
    receipt = AdaptiveHopReceiptV1.model_validate(receipt)
    if (
        publication.session_id != receipt.session_id
        or publication.input_manifest_sha256 != input_manifest_sha256
    ):
        raise ValueError("adaptive GLRT publication is bound to a different capture")
    evidence = publication.evidence
    if evidence is None:
        return
    if (
        evidence.session != persistent_hop_wire_session_id(receipt.session_id)
        or evidence.generation != receipt.plan.policy.generation
        or evidence.negotiated
        and evidence.mode != "positive-only-v1"
    ):
        raise ValueError("adaptive GLRT session, policy generation or profile changed")
    if evidence.source_terminal_attested and evidence.expected_results != len(receipt.events):
        raise ValueError("adaptive GLRT terminal inventory differs from started events")
    source_end = min(receipt.terminal.final_counter, receipt.terminal.last_block_end_counter)
    for result in evidence.results:
        if result.verdict == "no_signal":
            raise ValueError("positive-only adaptive GLRT cannot assert signal absence")
        if result.visit >= len(receipt.events):
            raise ValueError("adaptive GLRT result names an unobserved source event")
        event = receipt.events[result.visit]
        if (
            result.rate_hz != receipt.plan.geometry.sample_rate_hz
            or result.rx != receipt.plan.classification_receiver
            or result.channel != event.target.channel
            or result.edge != event.target.edge
            or result.valid_start != event.valid_start_counter
            or result.valid_end
            != event.valid_start_counter + receipt.plan.geometry.valid_visit_samples
        ):
            raise ValueError("adaptive GLRT result differs from actual source target/interval")
        if result.search_end > result.search_start and result.search_end > source_end:
            raise ValueError("adaptive GLRT searched beyond delivered capture IQ")
