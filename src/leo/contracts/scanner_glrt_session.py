"""Independent GLRT delivery evidence; existing capture receipts are unchanged."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.scanner_glrt_frame import U64, Digest, ScannerGlrtClassificationV1


class ScannerGlrtSessionEvidenceV1(ContractModel):
    schema_version: Literal[1] = 1
    kind: Literal["scanner_glrt_session_evidence"] = "scanner_glrt_session_evidence"
    session: U64
    generation: U64
    algorithm_sha256: Digest
    configuration_sha256: Digest
    negotiated: Annotated[bool, Field(strict=True)]
    mode: Annotated[str, Field(min_length=1, max_length=64)] | None
    source_terminal_attested: Annotated[bool, Field(strict=True)]
    final_received: Annotated[bool, Field(strict=True)]
    expected_results: Annotated[int, Field(strict=True, ge=0, le=2500)] | None
    dropped_results: Annotated[int, Field(strict=True, ge=0, le=2500)]
    result_sequence_limit: Annotated[int, Field(strict=True, ge=0, le=2500)]
    results: Annotated[tuple[ScannerGlrtClassificationV1, ...], Field(max_length=2500)]
    delivery_complete: Annotated[bool, Field(strict=True)]
    classification_complete: Annotated[bool, Field(strict=True)]
    error: Annotated[str, Field(min_length=1, max_length=2048)] | None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if not self.session or not self.generation:
            raise ValueError("session and generation must be nonzero")
        if self.algorithm_sha256 == "0" * 64 or self.configuration_sha256 == "0" * 64:
            raise ValueError("explicit artifact identities required")
        if self.negotiated != (self.mode is not None):
            raise ValueError("only negotiated evidence has an accepted mode")
        if self.source_terminal_attested != (self.expected_results is not None):
            raise ValueError("expected inventory requires independent terminal attestation")
        if not self.negotiated and (self.final_received or self.results):
            raise ValueError("unsupported peers cannot supply classifier evidence")
        previous = -1
        visits = set()
        for result in self.results:
            if result.sequence <= previous or result.visit in visits or result.rx != 1:
                raise ValueError("results must be ordered, unique, and RX1-only")
            if result.sequence >= self.result_sequence_limit:
                raise ValueError("result exceeds generated inventory")
            if self.mode == "unqualified-evidence" and result.verdict != "unavailable":
                raise ValueError("unqualified mode cannot assert a classification")
            previous = result.sequence
            visits.add(result.visit)
        if self.dropped_results > self.result_sequence_limit:
            raise ValueError("dropped count exceeds generated inventory")
        complete = (
            self.negotiated
            and self.source_terminal_attested
            and self.final_received
            and self.error is None
            and self.dropped_results == 0
            and len(self.results) == self.expected_results == self.result_sequence_limit
            and visits == set(range(self.expected_results or 0))
            and tuple(r.sequence for r in self.results) == tuple(range(len(self.results)))
        )
        classified = (
            complete
            and bool(self.results)
            and all(r.verdict != "unavailable" for r in self.results)
        )
        if self.delivery_complete != complete or self.classification_complete != classified:
            raise ValueError("delivery and classification completeness must match evidence")
        return self
