"""Portable typed analysis-subject identities."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from leo.contracts.digests import Sha256Digest, canonical_digest

Component = Annotated[str, StringConstraints(min_length=1, max_length=128)]
GitSha = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]


class ScopeKind(StrEnum):
    RECEIVER_PATH = "receiver_path"
    RADIO = "radio"
    PAIRED = "paired"


class ScopeIdentityV1(BaseModel):
    """A reversible subject identity whose size is not constrained by queue keys."""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_assignment=True)

    schema_version: Literal[1] = 1
    kind: ScopeKind
    session_id: Component
    stream_id: Component | None = None
    radio_id: Component | None = None
    receiver_id: Annotated[int, Field(ge=0, le=32767)] | None = None
    synchronization_inventory_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def _shape_matches_kind(self) -> Self:
        fields = (
            self.stream_id,
            self.radio_id,
            self.receiver_id,
            self.synchronization_inventory_digest,
        )
        if self.kind is ScopeKind.RECEIVER_PATH:
            valid = self.stream_id is not None and self.receiver_id is not None
            valid = valid and self.radio_id is None and fields[3] is None
        elif self.kind is ScopeKind.RADIO:
            valid = self.stream_id is not None and self.radio_id is not None
            valid = valid and self.receiver_id is None and fields[3] is None
        else:
            valid = fields[:3] == (None, None, None) and fields[3] is not None
        if not valid:
            raise ValueError(f"scope fields do not match {self.kind.value!r}")
        return self

    @property
    def canonical_digest(self) -> Sha256Digest:
        return canonical_digest(self.model_dump(mode="json"))

    @classmethod
    def receiver_path(cls, *, session_id: str, stream_id: str, receiver_id: int) -> ScopeIdentityV1:
        return cls(
            kind=ScopeKind.RECEIVER_PATH,
            session_id=session_id,
            stream_id=stream_id,
            receiver_id=receiver_id,
        )

    @classmethod
    def radio(cls, *, session_id: str, stream_id: str, radio_id: str) -> ScopeIdentityV1:
        return cls(
            kind=ScopeKind.RADIO,
            session_id=session_id,
            stream_id=stream_id,
            radio_id=radio_id,
        )

    @classmethod
    def paired(cls, *, session_id: str, synchronization_inventory_digest: str) -> ScopeIdentityV1:
        return cls(
            kind=ScopeKind.PAIRED,
            session_id=session_id,
            synchronization_inventory_digest=synchronization_inventory_digest,
        )
