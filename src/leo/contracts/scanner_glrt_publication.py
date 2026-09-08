"""Additive publication binding radio-side GLRT evidence to a sealed capture."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest
from leo.contracts.scanner_glrt_frame import U64, Digest
from leo.contracts.scanner_glrt_session import ScannerGlrtSessionEvidenceV1

GLRT_SESSION_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"


class ScannerGlrtPublicationV1(ContractModel):
    schema_version: Literal[1] = 1
    kind: Literal["scanner_glrt_publication"] = "scanner_glrt_publication"
    session_id: Annotated[str, Field(pattern=GLRT_SESSION_PATTERN)]
    input_manifest_sha256: Sha256Digest
    algorithm_sha256: Digest
    configuration_sha256: Digest
    published_utc_ns: U64
    evidence: ScannerGlrtSessionEvidenceV1 | None
    error: Annotated[str, Field(min_length=1, max_length=2048)] | None

    @model_validator(mode="after")
    def _bound(self) -> Self:
        if self.algorithm_sha256 == "0" * 64 or self.configuration_sha256 == "0" * 64:
            raise ValueError("publication requires explicit requested classifier identities")
        if self.evidence is None and self.error is None:
            raise ValueError("missing classifier evidence requires an explicit error")
        if self.evidence is not None and (
            self.evidence.algorithm_sha256 != self.algorithm_sha256
            or self.evidence.configuration_sha256 != self.configuration_sha256
        ):
            raise ValueError("published evidence differs from requested classifier identities")
        return self
